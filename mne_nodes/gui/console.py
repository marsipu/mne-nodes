"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes

Simplified plain-text console with robust progress pinning.
Replaces earlier HTML/block based implementation to eliminate blank lines,
missing output, and fragile progress rendering.
"""

from __future__ import annotations

import codecs
import logging
import re
import sys
import time
import queue

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

from mne_nodes.gui.base_widgets import SimpleList
from mne_nodes.gui.code_editor import PythonHighlighter


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

    def __init__(
        self, kind: str, flush_interval_ms: int = 10000, max_chunk_size: int = 5000
    ):
        super().__init__()
        self.setAutoDelete(False)
        self.kind = kind
        self.flush_interval_ms = flush_interval_ms
        self.max_chunk_size = max_chunk_size
        self.signals = StreamWorkerSignals()
        self._mutex = QMutex()
        self._cond = QWaitCondition()
        # Queue with max size to prevent memory overload and lag
        self.queue = queue.Queue(1000)
        self._dropped_count = 0  # Track dropped items due to queue overflow
        self.chunk: str = ""
        self.chunk_len: int = 0
        self.progress_line: str | None = None
        self.last_emitted: float = time.monotonic()
        self._stopping = False
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        QThreadPool.globalInstance().start(self)

    # Public API ---------------------------------------------------------
    def push(self, data, kind: str):
        try:
            self.queue.put_nowait((data, kind))
        except queue.Full:
            # Drop oldest item
            self.queue.get_nowait()
            self._dropped_count += 1
            # Log warning periodically (every 10th drop)
            if self._dropped_count % 10 == 1:
                logging.warning(
                    f"Console {self.kind} queue full, "
                    f"dropped {self._dropped_count} items total"
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

    def _emit_chunk(self, chunk: str):
        """Emit text and progress updates from a chunk.

        Processes ALL intermediate progress updates (not just the last
        one) to provide smooth progress rendering when multiple updates
        occur between flushes.
        """
        if not chunk:
            return

        if "\r" in chunk:
            parts = chunk.split("\r")

            # Emit first part as normal text (before any progress)
            if parts[0]:
                self.signals.text_ready.emit(parts[0], self.kind)

            # Process ALL intermediate progress updates
            for i in range(1, len(parts)):
                part = parts[i]
                if not part:
                    continue

                # Check if this segment has newlines (progress finished + new text)
                if "\n" in part:
                    lines = part.split("\n")
                    prog_line = lines[0]
                    rest = "\n".join(lines[1:])

                    if prog_line:
                        finished = self._detect_finished(prog_line)
                        self.signals.progress_ready.emit(prog_line, finished)

                    # Emit trailing text AFTER progress update
                    if rest:
                        self.signals.text_ready.emit(rest, self.kind)
                else:
                    # Pure progress line (no newline yet)
                    finished = self._detect_finished(part)
                    self.signals.progress_ready.emit(part, finished)
            return

        # Normal case (no carriage returns)
        self.signals.text_ready.emit(chunk, self.kind)

    # QRunnable run ------------------------------------------------------
    def run(self):
        while True:
            now = time.monotonic()
            data, kind = self.queue.get(block=True)
            # Convert bytes data
            if isinstance(data, (bytes, bytearray)):
                data = self._decoder.decode(data, final=True)
            # Convert to html
            data = data.replace("<", "&lt;")
            data = data.replace(">", "&gt;")
            data = data.replace("\n", "<br>")
            data = data.replace("\x1b", "")
            # Process handling
            if "\r" in data:
                data = f"<span style='color:green;'>{data}</span>"
                self._progress_line = data
                if now - self.last_emitted >= self.flush_interval_ms / 1000.0:
                    finished = self._detect_finished(data)
                    self.signals.progress_ready.emit(data, finished)
                    self.last_emitted = now
                continue
            elif kind == "stderr":
                data = f"<span style='color:red;'>{data}</span>"
            self.chunk += data
            self.chunk_len += len(data)

            # Emit chunk if too large or flush interval passed
            if (
                self.chunk_len >= self.max_chunk_size
                or now - self.last_emitted >= self.flush_interval_ms / 1000.0
            ):
                # Reset chunk
                chunk = self.chunk
                self.chunk = ""
                self.signals.text_ready.emit(chunk)
                self.last_emitted = now

            # Stop if necessary
            if self._stopping and self.queue.empty():
                break


# ---------------------------------------------------------------------------
# Console (plain text + progress pinning)
# ---------------------------------------------------------------------------
class ConsoleWidget(QPlainTextEdit):
    """Plain text console keeping an in-progress status line pinned at
    bottom."""

    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setFont(QFont("Consolas", 12))
        self.autoscroll = True
        self.buffer_time = 50
        self._stream_workers: dict[str, StreamWorker] = {}
        self._progress_line: str | None = None
        self.setMaximumBlockCount(60000)
        self.destroyed.connect(lambda _=None: self.stop_streams())

    # # Compatibility (tests call these) ----------------------------------
    # def appendHtml(self, html: str):  # noqa: N802
    #     # Interpret <br> as newline and append
    #     text = html.replace("<br>", "\n")
    #     if text.endswith("\n"):
    #         text = text[:-1]
    #     for line in text.split("\n"):
    #         self._append_normal_line(line)
    #
    # def appendHtml(self, html: str):  # noqa: D401
    #     self.appendHtml(html)

    # Streams ------------------------------------------------------------
    def add_stream_worker(
        self,
        kind: str,
        flush_interval_ms: int | None = None,
        max_chunk_size: int = 8192,
    ):
        if kind in self._stream_workers:
            return self._stream_workers[kind]
        worker = StreamWorker(
            kind, flush_interval_ms or self.buffer_time, max_chunk_size
        )
        worker.signals.text_ready.connect(self._on_text)
        worker.signals.progress_ready.connect(self._on_progress)
        self._stream_workers[kind] = worker
        return worker

    def get_stream_worker(self, kind: str):
        return self._stream_workers.get(kind)

    def push_stdout(self, text):
        worker = self.get_stream_worker("stdout")
        if worker:
            worker.push(text)

    def push_stderr(self, text):
        worker = self.get_stream_worker("stderr")
        if worker:
            worker.push(text)

    def stop_streams(self):
        for w in self._stream_workers.values():
            w.stop()
        self._stream_workers.clear()
        self._progress_line = None

    # Internal line operations ------------------------------------------
    def _remove_last_line(self):
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.select(QTextCursor.SelectionType.LineUnderCursor)
        selected = cursor.selectedText()
        if selected:
            cursor.removeSelectedText()
            if cursor.position() > 0:
                cursor.deletePreviousChar()  # remove preceding newline
        self.setTextCursor(cursor)

    # Slots --------------------------------------------------------------
    def _on_text(self, text: str):
        # Handle progress line pinning
        if self._progress_line is not None:
            self._remove_last_line()
        self.appendHtml(text)
        if self._progress_line is not None:
            self.appendHtml(self._progress_line)

    def _on_progress(self, line: str, finished: bool):
        if self._progress_line is not None:
            self._remove_last_line()
        self.appendHtml(line)
        if finished:
            # finalize by adding newline so subsequent output starts on next line
            cursor = self.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.insertText("\n")
            self._progress_active = False
            self._progress_line = None
        else:
            self._progress_active = True
            self._progress_line = line

    # Event overrides ----------------------------------------------------
    def mousePressEvent(self, event):  # noqa: D401
        event.accept()

    def mouseDoubleClickEvent(self, event):  # noqa: D401
        event.accept()


class MainConsoleWidget(ConsoleWidget):
    def __init__(self):
        super().__init__()
        self.add_stream_worker("stdout", self.buffer_time)
        self.add_stream_worker("stderr", self.buffer_time)
        sys.stdout.signal.text_written.connect(self.push_stdout)
        sys.stderr.signal.text_written.connect(self.push_stderr)


# ---------------------------------------------------------------------------
# Notification / Error UI
# ---------------------------------------------------------------------------
class NotificationTabs(QTabWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
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


class ShowErrorWidget(QPlainTextEdit):
    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        self.setFont(QFont("Consolas", 12))
        self.highlighter = PythonHighlighter(self.document())


class ErrorWidget(QWidget):
    notification_count_changed = Signal(int)

    def __init__(self, controller):
        super().__init__()
        self.ct = controller
        layout = QHBoxLayout(self)
        self.list_widget = SimpleList()
        layout.addWidget(self.list_widget)
        self.show_widget = ShowErrorWidget()
        layout.addWidget(self.show_widget, stretch=2)
        self._last_data = None
        self._count = 0

    @property
    def last_data(self):
        return self._last_data

    @last_data.setter
    def last_data(self, data):
        self._last_data = data
        if isinstance(data, (bytes, bytearray)):
            text = data.decode("utf-8", errors="replace")
        else:
            text = str(data)
        if text:
            self.show_widget.appendPlainText(text.rstrip("\n"))
        self._count += 1
        self.notification_count_changed.emit(self._count)

    def reset_count(self):
        self._count = 0
        self.notification_count_changed.emit(self._count)


class ConsoleDock(QDockWidget):
    def __init__(self, controller, parent=None):
        super().__init__("Console", parent)
        self.ct = controller
        self.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea
            | Qt.DockWidgetArea.BottomDockWidgetArea
        )
        self.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        self.process_tabs: dict[int, dict[str, object]] = {}
        self._process_tab_indexes: dict[int, int] = {}
        self.tab_widget = NotificationTabs(self)
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setMovable(False)
        self.tab_widget.setDocumentMode(False)
        self.tab_widget.tabCloseRequested.connect(self._close_process_tab)
        self.setWidget(self.tab_widget)

    def add_process(self, process_idx, title=None):
        if process_idx in self.process_tabs:
            return
        tab_title = title or f"Process {process_idx}"
        console = ConsoleWidget()
        console.add_stream_worker("stdout")
        console.add_stream_worker("stderr")
        err = ErrorWidget(self.ct)
        inner = NotificationTabs()
        inner.setDocumentMode(True)
        inner.setMovable(False)
        inner.setTabsClosable(False)
        inner.add_tab(console, "Console", 0)
        inner.add_tab(err, "Errors", 0)
        inner.currentChanged.connect(
            lambda idx, tabs=inner, e=err: self.reset_errors(idx, tabs, e)
        )
        err.notification_count_changed.connect(
            lambda c, pid=process_idx: self._update_process_notification(pid, c)
        )
        err.notification_count_changed.connect(
            lambda c, tabs=inner: tabs.set_notification(tab_name="Errors", count=c)
        )
        self.tab_widget.add_tab(inner, tab_title, count=0)
        idx = self.tab_widget._resolve(tab_name=tab_title)
        self.process_tabs[process_idx] = {
            "inner": inner,
            "console": console,
            "error": err,
        }
        self._process_tab_indexes[process_idx] = idx
        if not self.isVisible():
            self.setVisible(True)

    def _update_process_notification(self, process_idx, count):
        idx = self._process_tab_indexes.get(process_idx)
        if idx is None:
            return
        self.tab_widget.set_notification(tab_index=idx, count=count)
        title = f"Process {process_idx}"
        idx2 = self.tab_widget._resolve(tab_name=title)
        self._process_tab_indexes[process_idx] = idx2
        self.tab_widget.set_notification(tab_index=idx2, count=count)

    def reset_errors(self, idx, tabs: QTabWidget, err_widget: ErrorWidget):
        if tabs.tabText(idx) == "Errors":
            err_widget.reset_count()
            if isinstance(tabs, NotificationTabs):
                tabs.set_notification(tab_name="Errors", count=0)

    def push_stdout(self, process_idx, data):
        proc = self.process_tabs.get(process_idx)
        if not proc:
            return
        stream = proc["console"].get_stream_worker("stdout")  # type: ignore[index]
        if stream:
            stream.push(data)

    def push_stderr(self, process_idx, data):
        proc = self.process_tabs.get(process_idx)
        if not proc:
            return
        stream = proc["console"].get_stream_worker("stderr")  # type: ignore[index]
        if stream:
            stream.push(data)
        proc["error"].last_data = data  # type: ignore[index]

    def process_finished(self, process_idx):
        proc = self.process_tabs.get(process_idx)
        if proc:
            proc["console"].stop_streams()  # type: ignore[index]

    def stop_all(self):
        for proc in list(self.process_tabs.values()):
            proc["console"].stop_streams()  # type: ignore[index]

    def _close_process_tab(self, tab_index):
        pid = None
        for k, v in list(self._process_tab_indexes.items()):
            if v == tab_index:
                pid = k
                break
        self.tab_widget.remove_tab(tab_index=tab_index)
        if pid is not None:
            proc = self.process_tabs.pop(pid)
            self._process_tab_indexes.pop(pid)
            if proc:
                proc["console"].stop_streams()  # type: ignore[index]
        for k, v in list(self._process_tab_indexes.items()):
            if v > tab_index:
                self._process_tab_indexes[k] = v - 1
