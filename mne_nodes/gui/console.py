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
import io
import re
import sys
import time

# Added: import compatibility enums
from mne_nodes.qt_compat import (ELIDE_RIGHT, ALIGN_CENTER, ALIGN_RIGHT, LEFT_DOCK,
                                 RIGHT_DOCK, BOTTOM_DOCK, WA_DELETE_ON_CLOSE, )
from qtpy.QtCore import QMutex, QWaitCondition, QRunnable, QThreadPool, QObject, Signal
from qtpy.QtCore import (Qt, )
from qtpy.QtGui import QTextCursor, QFont
from qtpy.QtWidgets import (QPlainTextEdit, QDockWidget, QTabWidget, QHBoxLayout,
                            QWidget, QLabel, QTabBar, )

from mne_nodes.gui.base_widgets import SimpleList
from mne_nodes.gui.code_editor import PythonHighlighter

# ---------------------------------------------------------------------------
# Stream worker (decoding + progress detection)
# ---------------------------------------------------------------------------


class StreamWorkerSignals(QObject):
    text_ready = Signal(str)  # normal text (plain)
    progress_ready = Signal(str, bool)  # progress line + finished flag


class StreamWorker(QRunnable):
    """Accumulates incoming bytes/str, decodes to UTF-8, detects progress
    lines.

    Rules:
    - Carriage return ('\r') indicates an in-place progress update. Only the
      final segment after the last '\r' is treated as current progress.
    - If that segment contains newlines, the first line is progress, remaining
      lines are normal output (emitted BEFORE progress so the progress line
      remains visually last while active).
    - Progress is considered finished if pattern N/N or 100% is detected.
    """

    _RE_FRAC = re.compile(r"(\d+)\s*/\s*(\d+)")
    _RE_PERCENT = re.compile(r"(\d{1,3})\s*%")

    def __init__(
        self, kind: str, flush_interval_ms: int = 50, max_chunk_size: int = 8192
    ):
        super().__init__()
        self.setAutoDelete(False)
        self.kind = kind
        self.flush_interval_ms = flush_interval_ms
        self.max_chunk_size = max_chunk_size
        self.signals = StreamWorkerSignals()
        self._mutex = QMutex()
        self._cond = QWaitCondition()
        self._queue: list[tuple[str, bytes | str]] = []
        self._stopping = False
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        QThreadPool.globalInstance().start(self)

    # Public API ---------------------------------------------------------
    def push(self, data):
        self._mutex.lock()
        try:
            if isinstance(data, (bytes, bytearray)):
                self._queue.append(("b", bytes(data)))
            elif isinstance(data, str):
                self._queue.append(("s", data))
            else:  # fallback
                self._queue.append(("s", str(data)))
            self._cond.wakeOne()
        finally:
            self._mutex.unlock()

    def stop(self):
        self._mutex.lock()
        try:
            self._stopping = True
            self._cond.wakeOne()
        finally:
            self._mutex.unlock()

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
        if not chunk:
            return
        if "\r" in chunk:
            parts = chunk.split("\r")
            prefix = parts[0]
            if prefix:
                self.signals.text_ready.emit(prefix)
            last = parts[-1]
            if last:
                if "\n" in last:
                    prog_line, rest = last.split("\n", 1)
                else:
                    prog_line, rest = last, ""
                finished = self._detect_finished(prog_line)
                # Emit trailing normal text before progress so progress stays last
                if rest:
                    self.signals.text_ready.emit(rest)
                self.signals.progress_ready.emit(prog_line, finished)
            return
        # Normal case
        self.signals.text_ready.emit(chunk)

    # QRunnable run ------------------------------------------------------
    def run(self):
        acc: list[str] = []
        acc_len = 0
        last_emit = time.monotonic()
        while True:
            self._mutex.lock()
            try:
                if not self._queue and not self._stopping:
                    self._cond.wait(self._mutex, self.flush_interval_ms)
                items = self._queue
                self._queue = []
                stopping = self._stopping
            finally:
                self._mutex.unlock()

            now = time.monotonic()
            for typ, data in items:
                if typ == "b":
                    dec = self._decoder.decode(data)
                    if dec:
                        acc.append(dec)
                        acc_len += len(dec)
                else:
                    if data:
                        acc.append(data)  # type: ignore[arg-type]
                        acc_len += len(data)  # type: ignore[arg-type]

            if acc_len and (
                acc_len >= self.max_chunk_size
                or (now - last_emit) >= (self.flush_interval_ms / 1000.0)
                or (stopping and not items)
            ):
                chunk = "".join(acc)
                acc.clear()
                acc_len = 0
                self._emit_chunk(chunk)
                last_emit = now
            if stopping and not items and acc_len == 0:
                break

        rem = self._decoder.decode(b"", final=True)
        if rem:
            self._emit_chunk(rem)


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
        self._streams: dict[str, StreamWorker] = {}
        self._progress_active = False
        self._progress_line: str | None = None
        self.setMaximumBlockCount(60000)
        self.destroyed.connect(lambda _=None: self.stop_streams())

    # Compatibility (tests call these) ----------------------------------
    def appendHtml(self, html: str):  # noqa: N802
        # Interpret <br> as newline and append
        text = html.replace("<br>", "\n")
        if text.endswith("\n"):
            text = text[:-1]
        for line in text.split("\n"):
            self._append_normal_line(line)

    def write_html(self, html: str):  # noqa: D401
        self.appendHtml(html)

    # Streams ------------------------------------------------------------
    def add_stream(
        self,
        kind: str,
        flush_interval_ms: int | None = None,
        max_chunk_size: int = 8192,
    ):
        if kind in self._streams:
            return self._streams[kind]
        worker = StreamWorker(
            kind, flush_interval_ms or self.buffer_time, max_chunk_size
        )
        worker.signals.text_ready.connect(self._on_text)
        worker.signals.progress_ready.connect(self._on_progress)
        self._streams[kind] = worker
        return worker

    def get_stream(self, kind: str):
        return self._streams.get(kind)

    def stop_streams(self):
        for w in self._streams.values():
            w.stop()
        self._streams.clear()
        self._progress_active = False
        self._progress_line = None

    # Internal line operations ------------------------------------------
    def _append_normal_line(self, line: str):
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(line + "\n")
        if self.autoscroll:
            self.ensureCursorVisible()

    def _append_progress_line(self, line: str):
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(line)  # no newline so we can overwrite
        if self.autoscroll:
            self.ensureCursorVisible()

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
        if not text:
            return
        parts = text.split("\n")
        if self._progress_active:
            self._remove_last_line()
        for i, part in enumerate(parts):
            if not part and i == len(parts) - 1:
                continue  # trailing empty split artifact
            self._append_normal_line(part)
        if self._progress_active and self._progress_line is not None:
            self._append_progress_line(self._progress_line)

    def _on_progress(self, line: str, finished: bool):
        if self._progress_active:
            self._remove_last_line()
        self._append_progress_line(line)
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


# ---------------------------------------------------------------------------
# Stdout/Stderr redirection
# ---------------------------------------------------------------------------
class StreamSignals(QObject):
    text_written = Signal(str)


class StdoutStderrStream(io.TextIOBase):
    def __init__(self, kind):
        super().__init__()
        self.signal = StreamSignals()
        self.original_stream = sys.__stdout__ if kind == "stdout" else sys.__stderr__

    def write(self, text):  # type: ignore[override]
        try:
            if self.original_stream:
                self.original_stream.write(text)
        except OSError:
            pass
        self.signal.text_written.emit(text)

    def flush(self):  # type: ignore[override]
        try:
            if self.original_stream:
                self.original_stream.flush()
        except OSError:
            pass


class MainConsoleWidget(ConsoleWidget):
    def __init__(self):
        super().__init__()
        self.add_stream("stdout", self.buffer_time)
        self.add_stream("stderr", self.buffer_time)
        sys.stdout.signal.text_written.connect(
            lambda t: self.get_stream("stdout").push(t)
        )  # type: ignore[attr-defined]
        sys.stderr.signal.text_written.connect(
            lambda t: self.get_stream("stderr").push(t)
        )  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Notification / Error UI
# ---------------------------------------------------------------------------
class NotificationTabs(QTabWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.bubbles = {}
        self.tabBar().setElideMode(ELIDE_RIGHT)

    def add_tab(self, widget, tab_name, count=0):
        bubble = QLabel(str(count))
        bubble.setAlignment(ALIGN_CENTER)
        bubble.setStyleSheet(
            """background-color: red; color: white; border-radius: 8px; min-width: 16px; min-height: 16px; font-weight: bold; padding: 0 4px; font-size: 10pt;"""
        )
        index = self.addTab(widget, tab_name)
        bubble_container = QWidget()
        layout = QHBoxLayout(bubble_container)
        layout.setContentsMargins(8, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(bubble, 0, ALIGN_RIGHT)
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
        self.setAllowedAreas(LEFT_DOCK | RIGHT_DOCK | BOTTOM_DOCK)
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
        console.add_stream("stdout")
        console.add_stream("stderr")
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
        stream = proc["console"].get_stream("stdout")  # type: ignore[index]
        if stream:
            stream.push(data)

    def push_stderr(self, process_idx, data):
        proc = self.process_tabs.get(process_idx)
        if not proc:
            return
        stream = proc["console"].get_stream("stderr")  # type: ignore[index]
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
