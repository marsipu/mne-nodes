"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

from __future__ import annotations

import sys
import codecs
import logging
import queue
import re
import time
from functools import wraps, partial

from PySide6.QtWidgets import QVBoxLayout, QPushButton
from qtpy.QtCore import (
    QMutex,
    QWaitCondition,
    QRunnable,
    QThreadPool,
    QObject,
    Signal,
    Qt,
)
from qtpy.QtGui import QTextCursor, QFont
from qtpy.QtWidgets import (
    QPlainTextEdit,
    QDockWidget,
    QTabWidget,
    QHBoxLayout,
    QWidget,
    QLabel,
    QTabBar,
)

from mne_nodes.gui.gui_utils import ask_user
from mne_nodes.pipeline.execution import Process
from mne_nodes.pipeline.streams import init_streams


# ---------------------------------------------------------------------------
# Stream worker (decoding + progress detection)
# ---------------------------------------------------------------------------
class StreamWorkerSignals(QObject):
    text_ready = Signal(str)
    progress_ready = Signal(str, bool)  # progress line + finished flag


class StreamWorker(QRunnable):
    """Accumulates incoming bytes/str, decodes to UTF-8, detects progress
    lines.

    Rules:
    - Carriage return ('\r') indicates an in-place progress update. All
      intermediate progress updates are emitted to provide smooth progress
      rendering.
    - If a segment contains newlines, the first line is progress, remaining
      lines are normal output (emitted AFTER progress update).
    - Progress is considered finished if pattern N/N or 100% is detected.
    - Queue size is limited to prevent memory issues on massive output bursts.
    """

    _RE_FRAC = re.compile(r"(\d+)\s*/\s*(\d+)")
    _RE_PERCENT = re.compile(r"(\d{1,3})\s*%")

    def __init__(self, flush_interval_ms: int = 50, max_chunk_size: int = 5000):
        super().__init__()
        self.setAutoDelete(False)
        self.flush_s = flush_interval_ms / 1000.0
        self.max_chunk_size = max_chunk_size
        self.signals = StreamWorkerSignals()
        self._mutex = QMutex()
        self._cond = QWaitCondition()
        # Queue with max size to prevent memory overload and lag
        self.queue = queue.Queue(1000)
        self._dropped_count = 0  # Track dropped items due to queue overflow
        self.chunk: str = ""
        self.chunk_len: int = 0
        self._ignore_next_newline = False
        self._finished = False
        self._console_busy = False
        self.debug_list = []
        self.last_emitted: float = time.monotonic()
        self._stopping = False
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        QThreadPool.globalInstance().start(self)

    # Public API ---------------------------------------------------------
    def push(self, data, kind: str):
        self.debug_list.append(data)
        try:
            self.queue.put_nowait((data, kind))
        except queue.Full:
            # Drop oldest item
            self.queue.get_nowait()
            self._dropped_count += 1
            # Log warning periodically (every 10th drop)
            if self._dropped_count % 10 == 1:
                logging.warning(
                    f"Console queue full, dropped {self._dropped_count} items total"
                )
            self.queue.put_nowait((data, kind))

    def stop(self):
        self._stopping = True

    # Internal helpers ---------------------------------------------------
    def _detect_finished(self, line: str) -> bool:
        m = self._RE_FRAC.search(line)
        if m and m.group(1) == m.group(2) and m.group(1) != "0":
            return True
        m2 = self._RE_PERCENT.search(line)
        if m2 and m2.group(1) == "100":
            return True
        return False

    def _emit_chunk(self, force: bool = False):
        # Emit chunk if too large or flush interval passed
        now = time.monotonic()
        t_enough = now - self.last_emitted >= self.flush_s
        if (
            (force or self.chunk_len >= self.max_chunk_size or t_enough)
            and len(self.chunk) > 0
            and not self._console_busy
        ):
            # Reset chunk
            chunk = self.chunk
            self.chunk = ""
            self.chunk_len = 0
            self.signals.text_ready.emit(chunk)
            self.last_emitted = now

    # QRunnable run ------------------------------------------------------
    def run(self):
        while True:
            try:
                data, kind = self.queue.get(block=True, timeout=self.flush_s / 1000.0)
            except queue.Empty:
                # Emit chunk if any
                self._emit_chunk(force=True)
                # Stop if necessary
                if self._stopping and self.queue.empty():
                    break
                else:
                    continue
            # Convert bytes data
            if isinstance(data, (bytes, bytearray)):
                data = self._decoder.decode(data, final=True)
            # Convert to html
            data = data.replace("<", "&lt;")
            data = data.replace(">", "&gt;")
            data = data.replace("\n", "<br>")
            # ToDo: Convert ANSI codes to HTML maybe with .ansi2html
            data = data.replace("\x1b[A", "")
            data = data.replace("\x1b[0m", "")

            # Ignore empty lines
            if len(data) == 0:
                continue
            # Carriage return: progress update
            if data[:1] == "\r":
                data = data[1:]
                data = f"<span style='color:green;'>{data}</span>"
                now = time.monotonic()
                t_enough = now - self.last_emitted >= self.flush_s / 1000.0
                finished = self._detect_finished(data)
                # Avoid to print the final progress line twice
                if finished and self._finished:
                    continue
                else:
                    self._finished = finished
                if t_enough or self._finished and not self._console_busy:
                    self.signals.progress_ready.emit(data, finished)
                    self.last_emitted = now
                continue
            elif kind == "stderr":
                data = f"<span style='color:red;'>{data}</span>"
            self.chunk += data
            self.chunk_len += len(data)
            self._emit_chunk()


# ---------------------------------------------------------------------------
# Console (plain text + progress pinning)
# ---------------------------------------------------------------------------
def busy_state(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        self.stream_worker._console_busy = True
        try:
            return func(self, *args, **kwargs)
        finally:
            self.stream_worker._console_busy = False

    return wrapper


class ConsoleWidget(QPlainTextEdit):
    """Plain text console keeping an in-progress status line pinned at
    bottom."""

    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setFont(QFont("Consolas", 12))
        self._progress_line: str | None = None
        self.autoscroll = True
        self.stream_worker = StreamWorker()
        self.stream_worker.signals.text_ready.connect(self._on_text)
        self.stream_worker.signals.progress_ready.connect(self._on_progress)
        self.setMaximumBlockCount(60000)
        self.destroyed.connect(lambda _=None: self.stop_streams())

    # Streams ------------------------------------------------------------
    def push_stdout(self, text):
        self.stream_worker.push(text, "stdout")

    def push_stderr(self, text):
        self.stream_worker.push(text, "stderr")

    def stop_streams(self):
        self.stream_worker.stop()
        self._progress_line = None

    # Internal line operations ------------------------------------------
    def add_text(self, text):
        self.textCursor().insertHtml(text)
        if self.autoscroll:
            self.ensureCursorVisible()

    def _remove_last_line(self):
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.select(QTextCursor.SelectionType.LineUnderCursor)
        selected = cursor.selectedText()
        if selected:
            cursor.removeSelectedText()  # self.setTextCursor(cursor)

    # Slots --------------------------------------------------------------
    @busy_state
    def _on_text(self, text: str):
        # Handle progress line pinning
        if self._progress_line is not None:
            self._remove_last_line()
        self.add_text(text)
        if self._progress_line is not None:
            self.add_text(self._progress_line)

    @busy_state
    def _on_progress(self, line: str, finished: bool):
        if self._progress_line is not None:
            self._remove_last_line()
        self.add_text(line)
        if finished:
            # # finalize by adding newline so subsequent output starts on next line
            # cursor = self.textCursor()
            # cursor.movePosition(QTextCursor.MoveOperation.End)
            # cursor.insertText("<br>")
            self._progress_active = False
            self._progress_line = None
        else:
            self._progress_active = True
            self._progress_line = line

    # Event overrides ----------------------------------------------------
    # The cursor should not be moved my mouse clicks
    def mousePressEvent(self, event):  # noqa: D401
        event.accept()

    def mouseDoubleClickEvent(self, event):  # noqa: D401
        event.accept()


class MainConsoleWidget(ConsoleWidget):
    def __init__(self):
        super().__init__()
        if not hasattr(sys.stdout, "signal") or not hasattr(sys.stderr, "signal"):
            logging.warning(
                "Streams have not been initialized as Qt-objects yet, initializing them now."
            )
            init_streams()
        sys.stdout.signal.text_written.connect(self.push_stdout)
        sys.stderr.signal.text_written.connect(self.push_stderr)


# ---------------------------------------------------------------------------
# Notification / Error UI
# ---------------------------------------------------------------------------
class NotificationTabs(QTabWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDocumentMode(True)
        self.setMovable(False)
        self.setTabsClosable(False)
        self.bubbles = {}
        self.tabBar().setElideMode(Qt.TextElideMode.ElideRight)

    def add_tab(self, widget, tab_name, count=0):
        bubble = QLabel(str(count))
        bubble.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bubble.setStyleSheet(
            """background-color: red; color: white; border-radius: 8px; min-width: 16px; min-height: 16px; font-weight: bold; padding: 0 4px; font-size: 10pt;"""
        )
        index = self.addTab(widget, tab_name)
        bubble_container = QWidget()
        layout = QHBoxLayout(bubble_container)
        layout.setContentsMargins(8, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(bubble, 0, Qt.AlignmentFlag.AlignRight)
        self.tabBar().setTabButton(
            index, QTabBar.ButtonPosition.RightSide, bubble_container
        )
        self.bubbles[index] = bubble
        bubble.setVisible(count != 0)

    def _resolve(self, tab_index=None, tab_name=None):
        if tab_index is not None:
            return tab_index
        if tab_name is None:
            raise ValueError("Need tab_index or tab_name")
        for i in range(self.count()):
            if self.tabText(i) == tab_name:
                return i
        raise ValueError(f"No tab named {tab_name}")

    def remove_tab(self, tab_index=None, tab_name=None):
        idx = self._resolve(tab_index, tab_name)
        if 0 <= idx < self.count():
            self.removeTab(idx)
            new = {}
            for i, bubble in self.bubbles.items():
                if i == idx:
                    bubble.setVisible(False)
                elif i > idx:
                    new[i - 1] = bubble
                else:
                    new[i] = bubble
            self.bubbles = new

    def set_notification(self, tab_index=None, tab_name=None, count=None):
        idx = self._resolve(tab_index, tab_name)
        bubble = self.bubbles.get(idx)
        if bubble is None:
            raise ValueError(f"No bubble for index {idx}")
        if count is not None:
            bubble.setText(str(count))
        bubble.setVisible(count != 0)


class ConsoleDock(QDockWidget):
    """A Console Dock containing multiple consoles.

    Rather than having error resolution here, it would be better to
    generate a report from the script and handling errors there too.
    """

    def __init__(self, controller, parent=None):
        super().__init__("Console", parent)
        self.ct = controller
        self.processes = {}
        self.consoles = {}
        self.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea
            | Qt.DockWidgetArea.BottomDockWidgetArea
        )
        self.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        self.tab_widget = QTabWidget(self)
        self.tab_widget.setMovable(False)
        self.tab_widget.setDocumentMode(False)
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self._close_process)
        self.setWidget(self.tab_widget)

    def start_process(self, program, arguments):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        console = ConsoleWidget()
        process_id = self.tab_widget.count()
        self.consoles[process_id] = console
        if not self.isVisible():
            self.setVisible(True)
        layout.addWidget(console)
        stop_bt = QPushButton("Stop")
        stop_bt.clicked.connect(partial(self._close_process, process_id))
        layout.addWidget(stop_bt)
        self.tab_widget.addTab(widget, f"Process {process_id}")
        self.tab_widget.setCurrentWidget(widget)
        # Create process
        process = Process(
            proc_id=process_id,
            console=console,
            working_directory=self.ct.deriv_root,
            self_destruct=True,
        )
        process.finished.connect(lambda _: self.processes.pop(process_id))
        self.processes[process_id] = process
        # Start process
        process.start(program, arguments)

    def _close_process(self, process_id):
        ans = ask_user(f"Do you really want to stop process {process_id}?")
        if ans:
            process = self.processes.get(process_id)
            process.kill()
            self.consoles.pop(process_id)
