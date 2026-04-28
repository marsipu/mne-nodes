"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import logging
import sys
from inspect import signature
from os.path import isdir

from qtpy.QtCore import QObject, Signal, QRunnable, Slot, QThreadPool, QProcess, Qt
from qtpy.QtGui import QFont
from qtpy.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QProgressBar,
    QHBoxLayout,
    QPushButton,
)

from mne_nodes.gui.console import MainConsoleWidget, ConsoleWidget
from mne_nodes.gui.gui_utils import set_ratio_geometry, warning_message
from mne_nodes.pipeline.exception_handling import get_exception_tuple, ExceptionTuple


class WorkerSignals(QObject):
    """Class for standard Worker-Signals."""

    # Emitted when the function finished and returns the return-value
    finished = Signal(object)

    # Emitted when the function throws an error and returns
    # a tuple with information about the error
    # (see get_exception_tuple)
    error = Signal(object)

    # Can be passed to function to be emitted when a part
    # of the function progresses to update a Progress-Bar
    pgbar_max = Signal(int)
    pgbar_n = Signal(int)
    pgbar_text = Signal(str)

    # Only an attribute which is stored here to maintain
    # reference when passing it to the function
    was_canceled = False


class Worker(QRunnable):
    """A class to execute a function in a seperate Thread.

    Parameters
    ----------
    function
        A reference to the function which is to be executed in the thread
    include_signals
        If to include the signals into the function-call
    args
        Any Arguments passed to the executed function
    kwargs
        Any Keyword-Arguments passed to the executed function
    """

    def __init__(self, function, *args, **kwargs):
        super().__init__()

        # Store constructor arguments (re-used for processing)
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        """Initialise the runner function with passed args, kwargs."""
        # Add signals to kwargs if in parameters of function
        if "worker_signals" in signature(self.function).parameters:
            self.kwargs["worker_signals"] = self.signals

        # Retrieve args/kwargs here; and fire processing using them
        try:
            return_value = self.function(*self.args, **self.kwargs)
        except Exception:  # noqa: BLE001
            exc_tuple = get_exception_tuple()
            self.signals.error.emit(exc_tuple)
        else:
            self.signals.finished.emit(return_value)  # Done

    def start(self):
        QThreadPool.globalInstance().start(self)

    def cancel(self):
        self.signals.was_canceled = True


class WorkerDialog(QDialog):
    """A Dialog for a Worker doing a function."""

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
        super().__init__(parent)

        self.show_buttons = show_buttons
        self.show_console = show_console
        self.close_directly = close_directly
        self.return_exception = return_exception
        self.title = title
        self.is_finished = False
        self.return_value = None

        # Initialize worker
        self.worker = Worker(function, **kwargs)
        self.worker.signals.finished.connect(self.on_thread_finished)
        self.worker.signals.error.connect(self.on_thread_finished)
        self.worker.signals.pgbar_max.connect(self.set_pgbar_max)
        self.worker.signals.pgbar_n.connect(self.pgbar_changed)
        self.worker.signals.pgbar_text.connect(self.label_changed)
        self.worker.start()

        if self.show_console:
            set_ratio_geometry(0.4, self)

        self.init_ui()
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

        self.progress_label = QLabel()
        self.progress_label.hide()
        layout.addWidget(self.progress_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.progress_bar = QProgressBar()
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        if self.show_console:
            self.console_output = MainConsoleWidget()
            layout.addWidget(self.console_output)

        if self.show_buttons:
            bt_layout = QHBoxLayout()

            cancel_bt = QPushButton("Cancel")
            cancel_bt.clicked.connect(self.cancel)
            bt_layout.addWidget(cancel_bt)

            self.close_bt = QPushButton("Close")
            self.close_bt.clicked.connect(self.close)
            self.close_bt.setEnabled(False)
            bt_layout.addWidget(self.close_bt)

            layout.addLayout(bt_layout)

        self.setLayout(layout)

    def on_thread_finished(self, return_value):
        # Store return value to send it when user closes the dialog
        if type(return_value) is ExceptionTuple and not self.return_exception:
            return_value = None
        self.return_value = return_value
        self.is_finished = True
        if self.show_buttons:
            self.close_bt.setEnabled(True)
        if self.close_directly:
            self.close()

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

    def closeEvent(self, event):
        # Can't close Dialog before Thread has finished or threw error
        if self.is_finished:
            self.thread_finished.emit(self.return_value)
            self.deleteLater()
            event.accept()
        else:
            warning_message(
                "Closing not possible! You can't close this Dialog before this Thread finished!",
                parent=self,
            )
            event.ignore()


class Process(QProcess):
    """A wrapper for QProcess.

    QProcess.start() can also multiple program/argument combinations in
    sequence.
    """

    allFinished = Signal(int, QProcess.ExitStatus)

    def __init__(
        self,
        commands=None,
        proc_id=None,
        console=None,
        working_directory=None,
        self_destruct=True,
    ):
        """
        Parameters
        ----------
        commands : list[tuple[str, list]] or None
            List of program/argument combinations to execute in sequence.
            The first element of each tuple is the program to execute,
            the second element is a list of arguments. If None, no commands
            are pre-registered. Then the process has to be started with
            explicit program/arguments.
        proc_id : int | None
            Optional ID for the process.
        console : ConsoleWidget | None
            Console to forward stdout/stderr to (if None, forwarding goes to stdout/stderr).
        working_directory : str | Path | None
            Working directory to set for each process.
        self_destruct : bool
            If True, the Process object will delete itself after finishing.
        """
        super().__init__()
        self.commands = commands or []
        self.proc_id = proc_id
        self.console = console
        if working_directory is not None and isdir(working_directory):
            self.setWorkingDirectory(str(working_directory))
        self.self_destruct = self_destruct
        self.readyReadStandardOutput.connect(self.handle_stdout)
        self.readyReadStandardError.connect(self.handle_stderr)
        self.stateChanged.connect(
            lambda state: logging.debug(
                f"Process {self.proc_id} state changed to {state.value}"
            )
        )
        self.finished.connect(self.handle_finished)

    def handle_finished(self, code, status):
        logging.info(
            f"Process {self.proc_id} finished with exit code {code} and status {status.value}."
        )
        # Start next process if necessary
        if len(self.commands) > 0:
            self.start()
        else:
            self.allFinished.emit(self.exitCode(), self.exitStatus())
            if self.console is not None:
                self.console.stop_streams()
            if self.self_destruct:
                self.deleteLater()

    def handle_error(self, error):
        logging.warning(f"Process {self.proc_id} encountered an error {error.value}.")

    def handle_stdout(self):
        text = self.readAllStandardOutput().data()
        if self.console is not None:
            self.console.push_stdout(text)
        else:
            sys.stdout.write(text)

    def handle_stderr(self):
        text = self.readAllStandardError().data()
        if self.console is not None:
            self.console.push_stderr(text)
        else:
            sys.stderr.write(text)

    def start(self, *args, **kwargs):
        # If commands are given to start(), execute them first
        if any([len(a) > 0 for a in [args, kwargs]]):
            logging.debug("Starting external commmand")
            super().start(*args, **kwargs)
            return
        # Otherwise, start the next command in the list
        if len(self.commands) > 0:
            cmds = self.commands.pop(0)
            # Start
            program, args = cmds
            self.setProgram(program)
            self.setArguments(args)
            super().start()
        else:
            logging.warning("Process.start() called but no commands left to execute.")


class ProcessDialog(QDialog):
    def __init__(
        self,
        parent,
        commands,
        show_buttons=True,
        show_console=True,
        close_directly=False,
        title=None,
        blocking=True,
    ):
        super().__init__(parent)
        self.commands = commands
        self.show_buttons = show_buttons
        self.show_console = show_console
        self.close_directly = close_directly
        self.title = title
        self.console = None

        self.process = None
        self.is_finished = False

        self.init_ui()
        self.start_process()

        set_ratio_geometry(0.5, self)

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

        if self.show_console:
            self.console = ConsoleWidget()
            layout.addWidget(self.console)

        if self.show_buttons:
            bt_layout = QHBoxLayout()

            cancel_bt = QPushButton("Cancel")
            cancel_bt.clicked.connect(self.process.kill)
            bt_layout.addWidget(cancel_bt)

            self.close_bt = QPushButton("Close")
            self.close_bt.clicked.connect(self.close)
            self.close_bt.setEnabled(False)
            bt_layout.addWidget(self.close_bt)

            layout.addLayout(bt_layout)

        self.setLayout(layout)

    def process_finished(self):
        self.is_finished = True
        if self.show_buttons:
            self.close_bt.setEnabled(True)
        if self.close_directly:
            self.close()

    def start_process(self):
        self.process = Process(self.commands, console=self.console, self_destruct=True)
        self.process.finished.connect(self.process_finished)
        self.process.start()

    def closeEvent(self, event):
        if self.is_finished:
            event.accept()
        else:
            event.ignore()
            warning_message(
                "Closing not possible! You can't close this Dialog before this Process finished!",
                parent=self,
            )
