"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import sys
import os
import shlex
from inspect import signature

from qtpy.QtCore import QObject, Signal, QRunnable, Slot, QThreadPool, QProcess, Qt
from qtpy.QtGui import QFont
from qtpy.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QProgressBar,
    QHBoxLayout,
    QPushButton,
    QMessageBox,
)

from mne_nodes.gui.console import MainConsoleWidget
from mne_nodes.gui.gui_utils import set_ratio_geometry
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
            QMessageBox.warning(
                self,
                "Closing not possible!",
                "You can't close this Dialog before this Thread finished!",
            )
            event.ignore()


class ProcessWorker(QObject):
    """A worker for QProcess.

    Unified abstraction for launching one or multiple external commands
    with stdout/stderr forwarding. Can be shared between MainWindow
    (pipeline execution) and QProcessDialog (update/install dialogs).
    """

    # Send decoded stdout from current process.
    stdoutSignal = Signal(str)
    # Send decoded stderr from current process.
    stderrSignal = Signal(str)
    # Emitted when all processes from commands are finished (no args, legacy behaviour)
    finished = Signal()
    # Detailed final finished signal of the current (last) process
    finishedDetailed = Signal(int, QProcess.ExitStatus)
    # Forward state changes of the current process
    stateChanged = Signal(QProcess.ProcessState)

    def __init__(self, commands, printtostd=True, working_directory=None):
        """
        Parameters
        ----------
        commands : str | list[str] | list[list[str]]
            Command or list of commands. Each command can be provided as a
            string (will be tokenized with shlex) or as a list of program + args.
        printtostd : bool
            Forward decoded stdout/stderr to sys.stdout/sys.stderr.
        working_directory : str | Path | None
            Working directory to set for each process.
        """
        super().__init__()

        # Normalize commands into list[list[str]] safely
        if not isinstance(commands, list):
            commands = [commands]
        normalized = []
        for cmd in commands:
            if isinstance(cmd, (list, tuple)):
                normalized.append([str(c) for c in cmd])
            else:
                # Tokenize respecting quotes; use posix flag depending on OS
                try:
                    normalized.append(shlex.split(str(cmd), posix=(os.name != "nt")))
                except ValueError:
                    # Fallback naive split
                    normalized.append(str(cmd).split(" "))
        self.commands = normalized
        self.printtostd = printtostd
        self.working_directory = working_directory
        self.process: QProcess | None = None
        self._current_exit_code = None
        self._current_exit_status = None

    @property
    def exit_code(self):
        return self._current_exit_code

    @property
    def exit_status(self):
        return self._current_exit_status

    def handle_stdout(self):
        if not self.process:
            return
        text = self.process.readAllStandardOutput().data().decode("utf8", "replace")
        self.stdoutSignal.emit(text)
        if self.printtostd:
            sys.stdout.write(text)

    def handle_stderr(self):
        if not self.process:
            return
        text = self.process.readAllStandardError().data().decode("utf8", "replace")
        self.stderrSignal.emit(text)
        if self.printtostd:
            sys.stderr.write(text)

    def error_occurred(self):
        if not self.process:
            return
        text = (
            f'An error occured with "{self.process.program()} '
            f'{" ".join(self.process.arguments())}":\n'
            f"{self.process.errorString()}\n"
        )
        self.stderrSignal.emit(text)
        if self.printtostd:
            sys.stderr.write(text)
        # Treat as finished for chaining
        # Pass synthetic exit code 1 if QProcess signals error
        self.process_finished(1, self.process.exitStatus())

    def process_finished(self, code, status):
        # Store last exit status
        self._current_exit_code = code
        self._current_exit_status = status
        if code == 1:
            text = (
                f'"{self.process.program()} '
                f'{" ".join(self.process.arguments())}" has crashed\n'
            )
            self.stderrSignal.emit(text)
            if self.printtostd:
                sys.stderr.write(text)
        if len(self.commands) > 0:
            self._start_next()
        else:
            # All done
            self.finishedDetailed.emit(code, status)
            self.finished.emit()

    def _start_next(self):
        # Take the first remaining command
        cmd = self.commands.pop(0)
        self.process = QProcess()
        if self.working_directory is not None:
            self.process.setWorkingDirectory(str(self.working_directory))
        # Wire signals
        self.process.errorOccurred.connect(self.error_occurred)
        self.process.readyReadStandardOutput.connect(self.handle_stdout)
        self.process.readyReadStandardError.connect(self.handle_stderr)
        self.process.stateChanged.connect(self.stateChanged)
        self.process.finished.connect(self.process_finished)
        # Start
        program, *args = cmd
        self.process.start(program, args)

    def start(self):
        # Only start if not already running
        if self.process is None:
            self._start_next()

    def kill(self, kill_all=False):
        if kill_all:
            self.commands = []
        if self.process:
            self.process.kill()


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
        controller=None,
    ):
        super().__init__(parent)
        self.commands = commands
        self.show_buttons = show_buttons
        self.show_console = show_console
        self.close_directly = close_directly
        self.title = title
        self.controller = controller
        self.proc_idx = None

        self.process_worker = None
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

    def process_finished(self):
        self.is_finished = True
        if self.show_buttons:
            self.close_bt.setEnabled(True)
        if self.close_directly:
            self.close()

    def cancel(self):
        self.process_worker.kill(kill_all=True)

    def start_process(self):
        # Use unified QProcessWorker, optionally register with controller
        if self.controller is not None:
            self.proc_idx, self.process_worker = self.controller.create_process_worker(
                self.commands, kind="dialog"
            )
        else:
            self.process_worker = ProcessWorker(self.commands)
        if self.show_console:
            self.console_output.add_stream_worker("stdout")
            self.console_output.add_stream_worker("stderr")
            self.process_worker.stdoutSignal.connect(
                lambda text: self.console_output.push_stdout(text)
            )
            self.process_worker.stderrSignal.connect(
                lambda text: self.console_output.push_stderr(text)
            )
        self.process_worker.finished.connect(self.process_finished)
        self.process_worker.start()

    def closeEvent(self, event):
        if self.is_finished:
            self.deleteLater()
            event.accept()
        else:
            event.ignore()
            QMessageBox.warning(
                self,
                "Closing not possible!",
                "You can't close the Dialog before this Process finished!",
            )
