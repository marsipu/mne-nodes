"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import io
import sys

from qtpy.QtCore import QTimer, QObject, Signal, Qt
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


class NotificationTabs(QTabWidget):
    """A QTabWidget with notification bubbles on the right side of each tab.

    Each tab can have a notification bubble that displays a count of
    notifications. The bubble is styled to be a small red circle with
    white text. The bubble is visible only when the count is greater
    than 0. The bubble can be updated to show a new count or hidden if
    the count is 0.
    """

    def __init__(self):
        super().__init__()
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
        layout.setContentsMargins(
            8, 0, 0, 0
        )  # add space between tab text and bubble, keep right flush
        layout.setSpacing(0)
        layout.addWidget(bubble, 0, Qt.AlignmentFlag.AlignRight)
        self.tabBar().setTabButton(
            index, QTabBar.ButtonPosition.RightSide, bubble_container
        )
        self.bubbles[index] = bubble
        bubble.setVisible(count != 0)

    def set_notification(self, tab_index=None, tab_name=None, count=None):
        """Set the notification count for a specific tab. If count is None, the
        bubble will not be updated. If count is 0, the bubble will be hidden.
        If count is greater than 0, the bubble will be shown with the count.

        Parameters
        ----------
        tab_index : int
            The index of the tab to update.
        tab_name : str
            The name of the tab to update. If provided, it will search for the tab by name.
            If both tab_index and tab_name are provided, tab_index will be used.
        count : int | None
            The notification count to set. If None, the bubble will not be updated.
        """
        if tab_index is None and tab_name is not None:
            # Resolve index by name
            for i in range(self.count()):
                if self.tabText(i) == tab_name:
                    tab_index = i
                    break
            if tab_index is None:
                raise ValueError(f"No tab found with name '{tab_name}'")
        elif tab_index is None and tab_name is None:
            raise ValueError("Either tab_index or tab_name must be provided.")

        bubble = self.bubbles.get(tab_index)
        if bubble is None:
            raise ValueError(f"No notification label found for tab index {tab_index}")

        if count is not None:
            bubble.setText(str(count))
        bubble.setVisible(count != 0)


class ConsoleDock(QDockWidget):
    """A dock widget for the main console widget."""

    def __init__(self, controller, parent=None):
        super().__init__("Console", parent)
        self.ct = controller
        self.tab_widget = QTabWidget()
        self.setWidget(self.tab_widget)

        # Add widget for consoles
        self.consoles_widget = ConsoleWidget()
        self.tab_widget.addTab(self.consoles_widget, "Console")

        self.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea
            | Qt.DockWidgetArea.BottomDockWidgetArea
        )
        self.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        self.error_widget = ErrorWidget(self.ct)
        self.tab_widget.addTab(self.error_widget, "Errors")


class ConsoleTabs(QTabWidget):
    """A tab widget to hold multiple console widgets."""

    def __init__(self):
        super().__init__()
        self.setTabsClosable(True)
        self.setMovable(False)
        self.setDocumentMode(True)

        # Add a main console tab
        self.main_console = MainConsoleWidget()
        self.addTab(self.main_console, "Main Console")

        # Connect the close event to remove the tab
        self.tabCloseRequested.connect(self.remove_tab)

    def remove_tab(self, index):
        if index >= 0 and index < self.count():
            self.removeTab(index)


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
