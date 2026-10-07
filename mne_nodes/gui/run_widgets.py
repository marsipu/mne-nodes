"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

from qtpy.QtCore import Qt, Signal
from qtpy.QtGui import QFont
from qtpy.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mne_nodes.gui.console import ConsoleWidget, MainConsoleWidget
from mne_nodes.gui.gui_utils import set_ratio_geometry, warning_message
from mne_nodes.pipeline.exception_handling import ExceptionTuple
from mne_nodes.pipeline.execution import Process, Worker


class _RunDialog(QDialog):
    def __init__(
        self,
        parent,
        show_buttons,
        show_console,
        close_directly,
        title,
        blocking,
        geometry_ratio,
    ):
        super().__init__(parent)

        self.show_buttons = show_buttons
        self.show_console = show_console
        self.close_directly = close_directly
        self.title = title
        self.is_finished = False

        self.init_ui()
        self.start_operation()
        set_ratio_geometry(geometry_ratio, self)
        if blocking:
            self.exec()
        else:
            self.open()

    def init_ui(self):
        layout = QVBoxLayout()

        if self.title:
            title_label = QLabel(self.title)
            title_label.setFont(QFont("AnyType", 18, QFont.Weight.Bold))
            layout.addWidget(title_label)

        self.init_content(layout)

        if self.show_buttons:
            bt_layout = QHBoxLayout()

            self.cancel_bt = QPushButton("Cancel")
            self.cancel_bt.clicked.connect(self.cancel)
            bt_layout.addWidget(self.cancel_bt)

            self.close_bt = QPushButton("Close")
            self.close_bt.clicked.connect(self.close)
            self.close_bt.setEnabled(False)
            bt_layout.addWidget(self.close_bt)

            layout.addLayout(bt_layout)

        self.setLayout(layout)

    def init_content(self, layout):
        raise NotImplementedError

    def start_operation(self):
        raise NotImplementedError

    def cancel(self):
        raise NotImplementedError

    def mark_finished(self):
        self.is_finished = True
        if self.show_buttons:
            self.close_bt.setEnabled(True)
            self.cancel_bt.setEnabled(False)
        if self.close_directly:
            self.close()

    def closeEvent(self, event):
        if self.is_finished:
            self.on_closed()
            event.accept()
        else:
            warning_message(
                "Closing not possible! You can't close this Dialog before this "
                "operation finished!",
                parent=self,
            )
            event.ignore()

    def on_closed(self):
        pass


class WorkerDialog(_RunDialog):
    """A Dialog for a Worker doing a function.

    This dialog manages the execution of a worker thread and provides UI elements
    for progress tracking and user interaction.

    Parameters
    ----------
    parent : QWidget
        Parent widget for this dialog.
    function : callable
        The function to be executed in the worker thread.
    show_buttons : bool, default False
        If True, displays Cancel and Close buttons.
    show_console : bool, default False
        If True, displays a console output widget.
    close_directly : bool, default True
        If True, closes the dialog automatically when the worker finishes.
    blocking : bool, default False
        If True, blocks execution until the dialog is closed (exec mode).
        If False, displays the dialog non-blocking (open mode).
    return_exception : bool, default False
        If True, returns exception information; otherwise returns None on error.
    title : str, optional
        Title to display at the top of the dialog.
    **kwargs
        Additional keyword arguments passed to the Worker.

    Signals
    -------
    thread_finished : Signal(object)
        Emitted when the worker thread finishes, carrying the return value.
    """

    thread_finished = Signal(object)

    def __init__(
        self,
        parent,
        function,
        show_buttons=False,
        show_console=False,
        close_directly=True,
        blocking=False,
        return_exception=False,
        title=None,
        **kwargs,
    ):
        self.return_exception = return_exception
        self.return_value = None

        self.worker = Worker(function, **kwargs)
        self.worker.signals.finished.connect(self.on_thread_finished)
        self.worker.signals.error.connect(self.on_thread_finished)
        self.worker.signals.pgbar_max.connect(self.set_pgbar_max)
        self.worker.signals.pgbar_n.connect(self.pgbar_changed)
        self.worker.signals.pgbar_text.connect(self.label_changed)
        super().__init__(
            parent, show_buttons, show_console, close_directly, title, blocking, 0.4
        )

    def start_operation(self):
        self.worker.start()

    def init_content(self, layout):
        self.progress_label = QLabel()
        self.progress_label.hide()
        layout.addWidget(self.progress_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.progress_bar = QProgressBar()
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        if self.show_console:
            self.console_output = MainConsoleWidget()
            layout.addWidget(self.console_output)

    def on_thread_finished(self, return_value):
        # Store return value to send it when user closes the dialog
        if type(return_value) is ExceptionTuple and not self.return_exception:
            return_value = None
        self.return_value = return_value
        self.mark_finished()

    def set_pgbar_max(self, maximum):
        self.progress_bar.show()
        self.progress_bar.setMaximum(maximum)

    def pgbar_changed(self, value):
        self.progress_bar.setValue(value)

    def label_changed(self, text):
        self.progress_label.show()
        self.progress_label.setText(text)

    def cancel(self):
        self.worker.cancel()

    def on_closed(self):
        self.thread_finished.emit(self.return_value)
        self.deleteLater()


class ProcessDialog(_RunDialog):
    def __init__(
        self,
        commands: list[tuple[str, ...]],
        parent: QWidget | None = None,
        show_buttons: bool = True,
        show_console: bool = True,
        close_directly: bool = False,
        title: str | None = None,
        blocking: bool = True,
    ):
        self.commands = commands
        self.console = None

        super().__init__(
            parent, show_buttons, show_console, close_directly, title, blocking, 0.5
        )

    def init_content(self, layout):
        if self.show_console:
            self.console = ConsoleWidget()
            layout.addWidget(self.console)

        self.process = Process(self.commands, console=self.console, self_destruct=True)
        self.process.finished.connect(self.process_finished)

    def start_operation(self):
        self.process.start()

    def cancel(self):
        self.process.kill()

    def process_finished(self):
        self.mark_finished()
