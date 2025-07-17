"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import io
import sys

from PySide6.QtCore import QTimer, QObject, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QPlainTextEdit


class ConsoleWidget(QPlainTextEdit):
    """A Widget displaying formatted stdout/stderr-output."""

    def __init__(self):
        super().__init__()

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
            cursor.select(QTextCursor.LineUnderCursor)
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
    """A subclass of ConsoleWidget which is linked to stdout/stderr of the main
    process."""

    def __init__(self):
        super().__init__()

        # Connect custom stdout and stderr to display-function
        sys.stdout.signal.text_written.connect(self.write_stdout)
        sys.stderr.signal.text_written.connect(self.write_stderr)


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
