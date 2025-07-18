"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import logging
import multiprocessing
import sys
import traceback
from contextlib import contextmanager

from PySide6.QtCore import QObject, Signal

from mne_nodes.gui.dialogs import ErrorDialog, show_error_dialog


class ExceptionTuple:
    def __init__(self, *args):
        self._data = [*args]

    def __getitem__(self, idx):
        return self._data[idx]

    def __setitem__(self, idx, value):
        self._data[idx] = value

    def __str__(self):
        return self._data[2]


def get_exception_tuple(is_mp=False):
    traceback.print_exc()
    exctype, value = sys.exc_info()[:2]
    traceback_str = traceback.format_exc(limit=-10)
    # ToDo: Is this doing what it's supposed to do?
    if is_mp:
        logger = multiprocessing.get_logging
    else:
        logger = logging.getLogger()
    logger.error(f"{exctype}: {value}")
    exc_tuple = ExceptionTuple(exctype, value, traceback_str)

    return exc_tuple


def gui_error_decorator(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception:
            exc_tuple = get_exception_tuple()
            ErrorDialog(exc_tuple)

    return wrapper


@contextmanager
def gui_error():
    try:
        yield
    except Exception:
        exc_tuple = get_exception_tuple()
        ErrorDialog(exc_tuple)


# ToDo: Test exception handling
class UncaughtHook(QObject):
    """This class is a modified version
    of https://timlehr.com/python-exception-hooks-with-qt-message-box/"""

    _exception_caught = Signal(object)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # connect signal to execute the message box function
        # always on main thread
        self._exception_caught.connect(show_error_dialog)

    def exception_hook(self, exc_type, exc_value, exc_traceback):
        """Function handling uncaught exceptions.

        It is triggered each time an uncaught exception occurs.
        """
        if issubclass(exc_type, KeyboardInterrupt):
            # ignore keyboard interrupt to support console applications
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
        else:
            # Error logging
            exc_info = (exc_type, exc_value, exc_traceback)
            exc_str = (
                exc_type.__name__,
                exc_value,
                "".join(traceback.format_tb(exc_traceback)),
            )
            logging.critical(
                "Uncaught exception:",
                exc_info=exc_info,
            )

            # trigger showing of error-dialog
            self._exception_caught.emit(exc_str)
