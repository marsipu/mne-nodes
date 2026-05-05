"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import logging
import sys
from inspect import signature
from os.path import isdir

from qtpy.QtCore import QObject, Signal, QRunnable, Slot, QThreadPool, QProcess

from mne_nodes.pipeline.exception_handling import get_exception_tuple


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
            lambda state: self._write_stdout(
                f"Process {self.proc_id} state changed to {state.value}"
            )
        )
        self.finished.connect(self.handle_finished)

    def handle_finished(self, code, status):
        self._write_stdout(
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

    def _write_stdout(self, text):
        if self.console is not None:
            self.console.push_stdout(text)
        else:
            sys.stdout.write(text)

    def _write_stderr(self, text):
        if self.console is not None:
            self.console.push_stderr(text)
        else:
            sys.stderr.write(text)

    def handle_error(self, error):
        logging.warning(f"Process {self.proc_id} encountered an error {error.value}.")

    def handle_stdout(self):
        text = self.readAllStandardOutput().data()
        self._write_stdout(text)

    def handle_stderr(self):
        text = self.readAllStandardError().data()
        self._write_stderr(text)

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
