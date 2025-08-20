"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import codecs
import io
import sys
import time

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


class ConsoleWidget(QPlainTextEdit):
    """A Widget displaying formatted stdout/stderr-output.

    This widget owns stream workers that decode and format text in a
    background QThread and emit HTML to be appended here at a controlled
    rate.
    """

    def __init__(self):
        super().__init__()
        self.setFont(QFont("Consolas", 12))
        self.highlighter = PythonHighlighter(self.document())
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))

        self.setReadOnly(True)
        self.autoscroll = True
        # Exposed for tests as the update cadence; used for worker timer
        self.buffer_time = 50

        # Kind -> StreamWorker mapping
        self._streams = {}

    def set_autoscroll(self, autoscroll):
        self.autoscroll = autoscroll

    # Public API: manage streams
    def add_stream(
        self,
        kind: str,
        flush_interval_ms: int | None = None,
        max_chunk_size: int = 8192,
    ):
        if kind in self._streams:
            return self._streams[kind]
        flush_interval_ms = flush_interval_ms or self.buffer_time
        worker = StreamWorker(kind, flush_interval_ms, max_chunk_size)
        worker.signals.html_ready.connect(self.write_html)
        worker.signals.progress_html_ready.connect(self.write_html_progress)
        self._streams[kind] = worker
        return worker

    def get_stream(self, kind: str):
        return self._streams.get(kind)

    def stop_streams(self):
        for w in self._streams.values():
            w.stop()
        self._streams.clear()

    # Slots to append pre-formatted HTML
    def write_html(self, text):
        if not text:
            return
        self.appendHtml(text)
        if self.autoscroll:
            self.ensureCursorVisible()

    def write_html_progress(self, text):
        if not text:
            return
        # Replace last line (progress update)
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.select(QTextCursor.SelectionType.LineUnderCursor)
        cursor.removeSelectedText()
        cursor.deletePreviousChar()
        self.appendHtml(text)
        if self.autoscroll:
            self.ensureCursorVisible()

    # Make sure cursor is not moved by mouse
    def mousePressEvent(self, event):
        event.accept()

    def mouseDoubleClickEvent(self, event):
        event.accept()


class StreamWorkerSignals(QObject):
    html_ready = Signal(str)
    progress_html_ready = Signal(str)


class StreamWorker(QRunnable):
    """Decode bytes or text, format to HTML, and emit at a controlled cadence.

    Pure QRunnable using a separate QObject for signals
    (StreamWorkerSignals). Call push(data) with bytes or str; call
    stop() to finish.
    """

    def __init__(
        self, kind: str, flush_interval_ms: int = 50, max_chunk_size: int = 8192
    ):
        super().__init__()
        QRunnable.setAutoDelete(self, False)
        self.kind = kind
        self.flush_interval_ms = flush_interval_ms
        self.max_chunk_size = max_chunk_size
        # Signals object (lives in GUI thread by default)
        self.signals = StreamWorkerSignals()
        # Shared state for the worker thread
        self._mutex = QMutex()
        self._cond = QWaitCondition()
        self._queue = []  # list[tuple[str, bytes|str]]
        self._stopping = False
        # Decoder and accumulators (used in run thread)
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        # Start on the global pool
        QThreadPool.globalInstance().start(self)

    # Public API from GUI thread
    def push(self, data):
        self._mutex.lock()
        try:
            if isinstance(data, (bytes, bytearray)):
                self._queue.append(("b", bytes(data)))
            elif isinstance(data, str):
                self._queue.append(("s", data))
            else:
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

    # Formatting helpers (run in worker thread)
    def _escape_and_convert(self, text: str) -> str:
        text = text.replace("<", "&lt;")
        text = text.replace(">", "&gt;")
        text = text.replace("\x1b", "")
        text = text.replace("\n", "<br>")
        return text

    def _format_html(self, text: str):
        if not text:
            return "", False
        # Progress handling if CR at the beginning of this batch
        if text[:1] == "\r":
            text = text.replace("\r", "")
            text = self._escape_and_convert(text)
            # Trim trailing <br> to avoid double breaks
            if text.endswith("<br>"):
                text = text[:-4]
            return f"<font color='green'>{text}</font>", True
        text = self._escape_and_convert(text)
        # Trim trailing <br> to avoid double breaks with appendHtml
        if text.endswith("<br>"):
            text = text[:-4]
        if self.kind == "stderr":
            return f'<font color="red">{text}</font>', False
        return text, False

    # QRunnable.run (executes in a thread pool thread)
    def run(self):
        acc = []
        acc_len = 0
        last_emit = time.monotonic()
        while True:
            # Wait for data or timeout
            self._mutex.lock()
            try:
                if not self._queue and not self._stopping:
                    self._cond.wait(self._mutex, self.flush_interval_ms)
                # Drain queue
                items = self._queue
                self._queue = []
                stopping = self._stopping
            finally:
                self._mutex.unlock()

            now = time.monotonic()
            # Process drained items
            for typ, data in items:
                if typ == "b":
                    decoded = self._decoder.decode(data)
                    if decoded:
                        acc.append(decoded)
                        acc_len += len(decoded)
                else:
                    if data:
                        acc.append(data)
                        acc_len += len(data)
            # Decide flush
            should_flush = acc_len > 0 and (
                acc_len >= self.max_chunk_size
                or (now - last_emit) >= (self.flush_interval_ms / 1000.0)
                or (stopping and not items)
            )
            if should_flush:
                text = "".join(acc)
                acc.clear()
                acc_len = 0
                formatted, is_progress = self._format_html(text)
                if formatted:
                    if is_progress:
                        self.signals.progress_html_ready.emit(formatted)
                    else:
                        self.signals.html_ready.emit(formatted)
                last_emit = now
            # Exit condition
            if stopping and not items and acc_len == 0:
                break
        # Final flush of decoder state
        rem = self._decoder.decode(b"", final=True)
        if rem:
            formatted, is_progress = self._format_html(rem)
            if formatted:
                if is_progress:
                    self.signals.progress_html_ready.emit(formatted)
                else:
                    self.signals.html_ready.emit(formatted)


class MainConsoleWidget(ConsoleWidget):
    def __init__(self):
        super().__init__()
        # Create streams for stdout/stderr and route text into them
        self.add_stream("stdout", self.buffer_time)
        self.add_stream("stderr", self.buffer_time)
        sys.stdout.signal.text_written.connect(
            lambda text: self.get_stream("stdout").push(text)
        )
        sys.stderr.signal.text_written.connect(
            lambda text: self.get_stream("stderr").push(text)
        )


class StreamSignals(QObject):
    text_written = Signal(str)


class StdoutStderrStream(io.TextIOBase):
    def __init__(self, kind):
        super().__init__()
        self.signal = StreamSignals()
        self.kind = kind
        if self.kind == "stdout":
            self.original_stream = sys.__stdout__
        elif self.kind == "stderr":
            self.original_stream = sys.__stderr__
        else:
            self.original_stream = None

    def write(self, text):
        if self.original_stream is not None:
            try:
                # Still send output to the command-line
                self.original_stream.write(text)
            except OSError:
                # In some test environments (e.g., Windows CI), the handle may be invalid.
                pass
        # Emit signal to display in GUI
        self.signal.text_written.emit(text)

    def flush(self):
        if self.original_stream is not None:
            try:
                self.original_stream.flush()
            except OSError:
                pass


class NotificationTabs(QTabWidget):
    """A QTabWidget with notification bubbles on the right side of each tab.

    Each tab can have a notification bubble that displays a count of
    notifications. The bubble is styled to be a small red circle with
    white text. The bubble is visible only when the count is greater
    than 0. The bubble can be updated to show a new count or hidden if
    the count is 0.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.bubbles = {}
        # Allow eliding to the right to avoid collision with the bubble
        self.tabBar().setElideMode(Qt.TextElideMode.ElideRight)

    def add_tab(self, widget, tab_name, count=0):
        bubble = QLabel(str(count))
        bubble.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bubble.setStyleSheet(
            """
            background-color: red;
            color: white;
            border-radius: 8px;
            min-width: 16px;
            min-height: 16px;
            font-weight: bold;
            padding: 0 4px;
            font-size: 10pt;
            """
        )
        index = self.addTab(widget, tab_name)
        # Wrap bubble in a right-side container with a small left margin to separate it from the text
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

    def _resolve_tab_index(self, tab_index=None, tab_name=None):
        if tab_index is not None:
            return tab_index
        if tab_name is None:
            raise ValueError("Either tab_index or tab_name must be provided.")
        for i in range(self.count()):
            if self.tabText(i) == tab_name:
                return i
        raise ValueError(f"No tab found with name '{tab_name}'")

    def remove_tab(self, tab_index=None, tab_name=None):
        tab_index = self._resolve_tab_index(tab_index, tab_name)
        if 0 <= tab_index < self.count():
            self.removeTab(tab_index)
            # Re-index bubbles to keep indices in sync after removal
            old_bubbles = self.bubbles
            new_bubbles = {}
            for idx, bubble in old_bubbles.items():
                if idx == tab_index:
                    bubble.setVisible(False)
                elif idx > tab_index:
                    new_bubbles[idx - 1] = bubble
                else:
                    new_bubbles[idx] = bubble
            self.bubbles = new_bubbles

    def set_notification(self, tab_index=None, tab_name=None, count=None):
        tab_index = self._resolve_tab_index(tab_index, tab_name)
        bubble = self.bubbles.get(tab_index)
        if bubble is None:
            raise ValueError(f"No notification label found for tab index {tab_index}")
        if count is not None:
            bubble.setText(str(count))
        bubble.setVisible(count != 0)


class ShowErrorWidget(QPlainTextEdit):
    """A widget to display error messages in a read-only text editor."""

    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        self.setFont(QFont("Consolas", 12))
        self.highlighter = PythonHighlighter(self.document())
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))


class ErrorWidget(QWidget):
    """A widget to display error messages and emit notification counts."""

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
        # Append to the display and update notification count
        try:
            if isinstance(data, (bytes, bytearray)):
                text = data.decode("utf-8", errors="replace")
            else:
                text = str(data)
            if text:
                self.show_widget.appendPlainText(text)
        except Exception:
            pass
        self._count += 1
        self.notification_count_changed.emit(self._count)

    def reset_count(self):
        self._count = 0
        self.notification_count_changed.emit(self._count)


class ConsoleDock(QDockWidget):
    """A dock widget that manages per-process tabs with Console and Errors."""

    def __init__(self, controller, parent=None):
        super().__init__("Console", parent)
        self.ct = controller
        self.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea
            | Qt.DockWidgetArea.BottomDockWidgetArea
        )
        self.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetFloatable)

        # Containers for process UI
        self.process_tabs = {}
        self._process_tab_indexes = {}

        # Top-level: one tab per process
        self.tab_widget = NotificationTabs(self)
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setMovable(False)
        self.tab_widget.setDocumentMode(False)
        self.tab_widget.tabCloseRequested.connect(self._close_process_tab)
        self.setWidget(self.tab_widget)

    # Process management API
    def add_process(self, process_idx, title=None):
        if process_idx in self.process_tabs:
            return
        tab_title = title or f"Process {process_idx}"

        # Console for stdout/stderr
        console = ConsoleWidget()
        console.add_stream("stdout")
        console.add_stream("stderr")

        # Error widget for this process
        err = ErrorWidget(self.ct)

        # Inner tabs: Console and Errors, with notification bubbles on tabs
        inner_tabs = NotificationTabs()
        inner_tabs.setDocumentMode(True)
        inner_tabs.setMovable(False)
        inner_tabs.setTabsClosable(False)
        inner_tabs.add_tab(console, "Console", count=0)  # no bubble usage
        inner_tabs.add_tab(err, "Errors", count=0)  # bubble updates here
        inner_tabs.currentChanged.connect(
            lambda idx,
            tabs=inner_tabs,
            e=err,
            pid=process_idx: self._maybe_reset_errors(idx, tabs, e, pid)
        )

        # Wire error count -> process tab bubble and inner Errors tab bubble
        err.notification_count_changed.connect(
            lambda count, pid=process_idx: self._update_process_notification(pid, count)
        )
        err.notification_count_changed.connect(
            lambda count, tabs=inner_tabs: tabs.set_notification(
                tab_name="Errors", count=count
            )
        )

        # Add inner tabs directly as the top-level process tab widget
        self.tab_widget.add_tab(inner_tabs, tab_title, count=0)
        idx = self.tab_widget._resolve_tab_index(tab_name=tab_title)

        self.process_tabs[process_idx] = {
            "inner": inner_tabs,
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
        try:
            self.tab_widget.set_notification(tab_index=idx, count=count)
        except Exception:
            # Try to recover index by tab text
            title = f"Process {process_idx}"
            try:
                idx2 = self.tab_widget._resolve_tab_index(tab_name=title)
                self._process_tab_indexes[process_idx] = idx2
                self.tab_widget.set_notification(tab_index=idx2, count=count)
            except Exception:
                pass

    def _maybe_reset_errors(
        self, idx, tabs: QTabWidget, err_widget: "ErrorWidget", process_idx
    ):
        # If the Errors tab is selected for this process, reset its notification count
        try:
            if tabs.tabText(idx) == "Errors":
                err_widget.reset_count()
                # also clear inner Errors tab bubble explicitly
                if isinstance(tabs, NotificationTabs):
                    tabs.set_notification(tab_name="Errors", count=0)
        except Exception:
            pass

    def push_stdout(self, process_idx, data):
        proc = self.process_tabs.get(process_idx)
        if proc is None:
            return
        stream = proc["console"].get_stream("stdout")
        if stream is not None:
            stream.push(data)

    def push_stderr(self, process_idx, data):
        proc = self.process_tabs.get(process_idx)
        if proc is None:
            return
        stream = proc["console"].get_stream("stderr")
        if stream is not None:
            stream.push(data)
        # Track last error data and increase notifications
        proc["error"].last_data = data

    def process_finished(self, process_idx):
        proc = self.process_tabs.get(process_idx)
        if proc is not None:
            proc["console"].stop_streams()

    def stop_all(self):
        for proc in list(self.process_tabs.values()):
            try:
                proc["console"].stop_streams()
            except Exception:
                pass

    def _close_process_tab(self, tab_index):
        # Find process by stored index
        pid = None
        for k, v in list(self._process_tab_indexes.items()):
            if v == tab_index:
                pid = k
                break
        # Remove the tab and reindex bubbles
        self.tab_widget.remove_tab(tab_index=tab_index)
        if pid is not None:
            proc = self.process_tabs.pop(pid, None)
            self._process_tab_indexes.pop(pid, None)
            if proc is not None:
                try:
                    proc["console"].stop_streams()
                except Exception:
                    pass
        # Shift stored indices above the removed index
        for k, v in list(self._process_tab_indexes.items()):
            if v > tab_index:
                self._process_tab_indexes[k] = v - 1
