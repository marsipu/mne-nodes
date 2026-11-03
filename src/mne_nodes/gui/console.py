"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

from __future__ import annotations

import codecs
import queue
import re
import sys
import time
from functools import wraps
from html import escape
from threading import Event

from ansi2html import Ansi2HTMLConverter
from qtpy.QtCore import QObject, QProcess, QRunnable, Qt, QThreadPool, Signal
from qtpy.QtGui import QFont, QTextCursor
from qtpy.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QTabBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from rich.ansi import AnsiDecoder

from mne_nodes.backend.execution import Process
from mne_nodes.backend.settings import Settings
from mne_nodes.backend.streams import init_streams
from mne_nodes.gui.user_interaction import ask_user
from mne_nodes.logger import logger


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
    - Carriage return ('\r') indicates an in-place progress update. Intermediate
      updates are coalesced at the flush interval.
    - If a segment contains newlines, the first line is progress, remaining
      lines are normal output (emitted AFTER progress update).
    - A newline finishes the current progress line.
    - Queue size is limited to prevent memory issues on massive output bursts.
    """

    _RE_CONTROL = re.compile(
        r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"
        r"|\x1b\[(?![\d;:]*m)[0-?]*[ -/]*[@-~]"
    )
    _RE_INCOMPLETE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*|\][^\x07\x1b]*\x1b?)?$")

    def __init__(self, flush_interval_ms: int = 50, max_chunk_size: int = 5000):
        super().__init__()
        self.setAutoDelete(False)
        self.flush_s = flush_interval_ms / 1000.0
        self.max_chunk_size = max_chunk_size
        self.signals = StreamWorkerSignals()
        self._render_ready = Event()
        self._render_ready.set()
        # Queue with max size to prevent memory overload and lag
        self.queue = queue.Queue(1000)
        self._dropped_count = 0  # Track dropped items due to queue overflow
        self.chunk: str = ""
        self.chunk_len: int = 0
        self._pending_progress = None
        self._progress_mode = False
        self._progress_text = ""
        self._progress_kind = None
        self.last_emitted: float = time.monotonic()
        self._stopping = False
        self._decoders = {
            kind: codecs.getincrementaldecoder("utf-8")(errors="replace")
            for kind in ("stdout", "stderr")
        }
        self._ansi_decoders = {kind: AnsiDecoder() for kind in self._decoders}
        self._incomplete = dict.fromkeys(self._decoders, "")
        self._carriage_return = dict.fromkeys(self._decoders, "")
        self._converter = Ansi2HTMLConverter(inline=True)
        QThreadPool.globalInstance().start(self)

    # Public API ---------------------------------------------------------
    def push(self, data, kind: str):
        for start in range(0, len(data), self.max_chunk_size):
            item = (data[start : start + self.max_chunk_size], kind)
            while True:
                try:
                    self.queue.put_nowait(item)
                    break
                except queue.Full:
                    try:
                        self.queue.get_nowait()
                    except queue.Empty:
                        continue
                    self._dropped_count += 1

    def stop(self):
        self._stopping = True
        self._render_ready.set()

    # Internal helpers ---------------------------------------------------
    def _emit_chunk(self, force: bool = False):
        # Emit chunk if too large or flush interval passed
        now = time.monotonic()
        t_enough = now - self.last_emitted >= self.flush_s
        if self.chunk and (force or self.chunk_len >= self.max_chunk_size or t_enough):
            self._wait_for_render()
            # Reset chunk
            chunk = self.chunk
            self.chunk = ""
            self.chunk_len = 0
            self._render_ready.clear()
            self.signals.text_ready.emit(chunk)
            self.last_emitted = now

    def _wait_for_render(self):
        while not self._render_ready.wait(self.flush_s):
            if self._stopping:
                break

    def _emit_progress(self, force: bool = False):
        if self._pending_progress is not None and (
            force or time.monotonic() - self.last_emitted >= self.flush_s
        ):
            self._emit_chunk(force=True)
            self._wait_for_render()
            line, kind, finished = self._pending_progress
            self._render_ready.clear()
            self.signals.progress_ready.emit(self._to_html(line, kind), finished)
            self._pending_progress = None
            self.last_emitted = time.monotonic()

    def _to_html(self, data: str, kind: str) -> str:
        decoder = self._ansi_decoders[kind]
        styled_output = "\x1b" in data or bool(decoder.style)
        if styled_output:
            # ansi2html converts fragments independently; Rich retains SGR state
            # between fragments without keeping the entire output history.
            styled = decoder.style.render(data, color_system="truecolor")
            for _ in decoder.decode(data):
                pass
            text = self._converter.convert(styled, full=False)
        else:
            text = escape(data)
        color = "color:red;" if kind == "stderr" and not styled_output else ""
        return f'<span style="{color}white-space:pre-wrap;">{text}</span>'

    # QRunnable run ------------------------------------------------------
    def run(self):
        while True:
            self._wait_for_render()
            try:
                data, kind = self.queue.get(block=True, timeout=self.flush_s)
            except queue.Empty:
                # Emit chunk if any
                self._emit_chunk(force=True)
                self._emit_progress(force=True)
                # Stop if necessary
                if self._stopping and self.queue.empty():
                    break
                else:
                    continue
            # Convert bytes data
            if isinstance(data, (bytes, bytearray)):
                data = self._decoders[kind].decode(data)
            data = self._incomplete[kind] + data
            self._incomplete[kind] = ""
            if match := self._RE_INCOMPLETE.search(data):
                self._incomplete[kind] = match.group()
                data = data[: match.start()]
            data = self._carriage_return[kind] + self._RE_CONTROL.sub("", data)
            self._carriage_return[kind] = "\r" if data.endswith("\r") else ""
            if self._carriage_return[kind]:
                data = data[:-1]
            data = data.replace("\r\n", "\n")
            for index, part in enumerate(data.split("\r")):
                if index:
                    self._progress_mode = True
                    self._progress_text = ""
                    self._progress_kind = kind
                if not part:
                    continue
                if self._progress_mode and kind == self._progress_kind:
                    line, newline, part = part.partition("\n")
                    self._progress_text += line
                    self._pending_progress = (self._progress_text, kind, bool(newline))
                    self._emit_progress(force=bool(newline))
                    if not newline:
                        continue
                    self._progress_mode = False
                if part:
                    self._emit_progress(force=True)
                    self.chunk += self._to_html(part, kind)
                    self.chunk_len += len(part)
                    self._emit_chunk()


# ---------------------------------------------------------------------------
# Console (plain text + progress pinning)
# ---------------------------------------------------------------------------
def busy_state(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        finally:
            self.stream_worker._render_ready.set()

    return wrapper


class ConsoleWidget(QPlainTextEdit):
    """Plain text console keeping an in-progress status line pinned at
    bottom."""

    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        self.set_word_wrap(Settings().get("console_word_wrap"))
        self.setFont(QFont("Consolas", 12))
        self._progress_line: str | None = None
        self.autoscroll = True
        self.stream_worker = StreamWorker()
        self.stream_worker.signals.text_ready.connect(self._on_text)
        self.stream_worker.signals.progress_ready.connect(self._on_progress)
        self.setMaximumBlockCount(60000)
        self.destroyed.connect(lambda _=None: self.stop_streams())

    # Streams ------------------------------------------------------------
    def set_word_wrap(self, enabled: bool) -> None:
        """Wrap long lines at the widget width or scroll horizontally."""
        mode = QPlainTextEdit.LineWrapMode
        self.setLineWrapMode(mode.WidgetWidth if enabled else mode.NoWrap)

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
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cursor.movePosition(
            QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor
        )
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
        self._remove_last_line()
        self.add_text(line)
        if finished:
            self.textCursor().insertBlock()
            self._progress_active = False
            self._progress_line = None
        else:
            self._progress_active = True
            self._progress_line = line

    # Event overrides ----------------------------------------------------
    # The cursor should not be moved my mouse clicks
    def mousePressEvent(self, event):
        event.accept()

    def mouseDoubleClickEvent(self, event):
        event.accept()


class MainConsoleWidget(ConsoleWidget):
    def __init__(self):
        super().__init__()
        if not hasattr(sys.stdout, "signal") or not hasattr(sys.stderr, "signal"):
            logger.warning(
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

    process_started = Signal()

    def __init__(self, controller, parent=None):
        super().__init__("Console", parent)
        self.ct = controller
        self.processes = []
        self.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea
            | Qt.DockWidgetArea.BottomDockWidgetArea
        )
        self.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        self.setMinimumWidth(self.screen().availableGeometry().width() // 4)
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
        process_idx = self.tab_widget.count()
        if not self.isVisible():
            self.setVisible(True)
        layout.addWidget(console)
        self.tab_widget.addTab(widget, f"Process {process_idx}")
        self.tab_widget.setCurrentWidget(widget)
        # Create process
        process = Process(
            proc_id=process_idx,
            console=console,
            working_directory=self.ct.deriv_root,
            self_destruct=True,
        )
        self.processes.append(process)
        process.started.connect(self.process_started)
        # Start process
        process.start(program, arguments)

    def _close_process(self, process_idx):
        process = self.processes[process_idx]
        try:
            if process.state() != QProcess.ProcessState.NotRunning:
                ans = ask_user(f"Do you really want to stop process {process_idx}?")
                if ans:
                    # Kill process
                    process.kill()
                else:
                    return
        except RuntimeError:
            logger.debug(f"Process {process_idx} already deleted.")
        # Remove process
        self.processes.pop(process_idx)
        # Remove tab
        widget = self.tab_widget.widget(process_idx)
        self.tab_widget.removeTab(process_idx)
        if widget is not None:
            widget.deleteLater()
