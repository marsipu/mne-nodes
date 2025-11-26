"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import logging
import sys
from pathlib import Path

from qtpy.QtCore import QObject, Signal
import io
from mne_nodes.pipeline.settings import Settings


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


def init_streams() -> None:
    # Redirect stdout and stderr to capture it later in GUI
    sys.stdout = StdoutStderrStream("stdout")
    sys.stderr = StdoutStderrStream("stderr")


def deinit_streams() -> None:
    """Restore original std streams.

    Switch sys.stdout/sys.stderr back to the interpreter defaults so
    subsequent code (pytest, terminal, other tests) no longer writes via
    Qt-backed redirection.
    """
    sys.stdout = sys.__stdout__
    sys.stderr = sys.__stderr__


def init_logging(debug_mode: bool = False) -> None:
    """Initialize Root Logger.

    Idempotent: replaces existing handlers named 'console'/'file' to avoid
    duplicate outputs when called multiple times (e.g., in tests).
    """
    logger = logging.getLogger()
    if debug_mode:
        logger.setLevel(logging.DEBUG)
        fmt = "{asctime} [{levelname}] {module}.{funcName}: {message}"
    else:
        logger.setLevel(Settings().get("log_level", default=logging.INFO))
        fmt = "[{levelname}] {message}"

    # Format console handler
    date_fmt = "%H:%M:%S"
    formatter = logging.Formatter(fmt, date_fmt, style="{")
    console_handler = logging.StreamHandler()
    console_handler.set_name("console")
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Format file handler
    logging_path = Settings().get("log_file_path") or Path.home() / "mne_nodes.log"
    file_handler = logging.FileHandler(logging_path, mode="w", encoding="utf-8")
    file_handler.set_name("file")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
