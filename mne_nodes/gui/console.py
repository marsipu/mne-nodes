"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import io
import sys

from qtpy.QtCore import QTimer, QObject, Signal, Qt
from qtpy.QtGui import QTextCursor, QFont
from qtpy.QtWidgets import QPlainTextEdit, QDockWidget, QTabWidget, QHBoxLayout, QWidget

from mne_nodes.gui.base_widgets import SimpleList
from mne_nodes.gui.code_editor import PythonHighlighter


class ConsoleWidget(QPlainTextEdit):
    """A Widget displaying formatted stdout/stderr-output."""

    def __init__(self):
        super().__init__()
        self.setFont(QFont("Consolas", 12))
        self.highlighter = PythonHighlighter(self.document())
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))

        self.setReadOnly(True)
        self.autoscroll = True
        self.is_progress = False

        # Buffer to avoid crash for too many inputs
        self.buffer = []
        self.buffer_time = 50
        self.buffer_timer = QTimer()
        self.buffer_timer.timeout.connect(self.write_buffer)
        self.buffer_timer.start(self.buffer_time)

    def write_buffer(self):
        if self.is_progress:
            # Delete last line
            cursor = self.textCursor()
            # Avoid having no break between progress and text
            # Remove last line
            cursor.select(QTextCursor.SelectionType.LineUnderCursor)
            cursor.removeSelectedText()
            cursor.deletePreviousChar()
            self.is_progress = False

        if len(self.buffer) > 0:
            text_list = self.buffer.copy()
            self.buffer.clear()
            text = "".join(text_list)
            # Remove last break because of appendHtml above
            if text[-4:] == "<br>":
                text = text[:-4]
            self.appendHtml(text)
            if self.autoscroll:
                self.ensureCursorVisible()

    def set_autoscroll(self, autoscroll):
        self.autoscroll = autoscroll

    def write_html(self, text):
        self.buffer.append(text)

    def _html_compatible(self, text):
        text = text.replace("<", "&lt;")
        text = text.replace(">", "&gt;")
        text = text.replace("\n", "<br>")
        text = text.replace("\x1b", "")

        if text[:1] == "\r":
            self.is_progress = True
            text = text.replace("\r", "")
            # Avoid having no break between progress and text
            text = f"<font color='green'>{text}</font>"
            if len(self.buffer) > 0:
                if self.buffer[-1][:20] == "<font color='green'>":
                    self.buffer.pop(-1)
        return text

    def write_stdout(self, text):
        text = self._html_compatible(text)
        self.buffer.append(text)

    def write_stderr(self, text):
        text = self._html_compatible(text)
        if text[-4:] == "<br>":
            text = f'<font color="red">{text[:-4]}</font><br>'
        else:
            text = f'<font color="red">{text}</font>'
        self.buffer.append(text)

    # Make sure cursor is not moved
    def mousePressEvent(self, event):
        event.accept()

    def mouseDoubleClickEvent(self, event):
        event.accept()


class MainConsoleWidget(ConsoleWidget):
    def __init__(self):
        super().__init__()
        # Connect custom stdout and stderr to display-function
        sys.stdout.signal.text_written.connect(self.write_stdout)
        sys.stderr.signal.text_written.connect(self.write_stderr)


class ConsoleDock(QDockWidget):
    """A dock widget for the main console widget."""

    def __init__(self, controller, parent=None):
        super().__init__("Console", parent)
        self.ct = controller
        self.tab_widget = QTabWidget()
        self.console_widget = ConsoleWidget()
        self.tab_widget.addTab(self.console_widget, "Console")

        self.setWidget(self.tab_widget)
        self.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.error_widget = ErrorWidget(self.ct)
        self.tab_widget.addTab(self.error_widget, "Errors")


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
            # Still send output to the command-line
            self.original_stream.write(text)
        # Emit signal to display in GUI
        self.signal.text_written.emit(text)

    def flush(self):
        if self.original_stream is not None:
            self.original_stream.flush()


class ShowErrorWidget(QPlainTextEdit):
    """A widget to display error messages in a read-only text editor."""

    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        self.setFont(QFont("Consolas", 12))
        self.highlighter = PythonHighlighter(self.document())
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))


class ErrorWidget(QWidget):
    """A widget to display error messages."""

    def __init__(self, controller):
        super().__init__()
        self.ct = controller
        layout = QHBoxLayout()
        self.list_widget = SimpleList()
        layout.addWidget(self.list_widget)
        self.show_widget = ShowErrorWidget()
        layout.addWidget(self.show_widget, stretch=2)
        self.setLayout(layout)

    def update_errors(self):
        pass
