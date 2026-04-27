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


_REDIRECTED_STREAMS: dict[str, StdoutStderrStream] = {}


def _has_stream_signal(stream: object) -> bool:
    """Return True when the stream has the Qt signal API used by the GUI."""
    signal = getattr(stream, "signal", None)
    return signal is not None and hasattr(signal, "text_written")


def get_redirected_stream(kind: str) -> StdoutStderrStream:
    """Return redirected stdout/stderr stream, restoring if replaced.

    Pytest and other tools may temporarily swap sys.stdout/sys.stderr.
    Ensure GUI widgets and logging handlers keep using the same stream object.
    """
    stream = _REDIRECTED_STREAMS.get(kind)
    if stream is None:
        current = sys.stdout if kind == "stdout" else sys.stderr
        if _has_stream_signal(current):
            stream = current
            _REDIRECTED_STREAMS[kind] = stream
        else:
            init_streams()
            stream = _REDIRECTED_STREAMS[kind]

    if kind == "stdout" and sys.stdout is not stream:
        sys.stdout = stream
    elif kind == "stderr" and sys.stderr is not stream:
        sys.stderr = stream
    return stream


def init_streams() -> None:
    # Redirect stdout and stderr to capture it later in GUI
    stdout_stream = StdoutStderrStream("stdout")
    stderr_stream = StdoutStderrStream("stderr")
    _REDIRECTED_STREAMS["stdout"] = stdout_stream
    _REDIRECTED_STREAMS["stderr"] = stderr_stream
    sys.stdout = stdout_stream
    sys.stderr = stderr_stream


def deinit_streams() -> None:
    """Restore original std streams.

    Switch sys.stdout/sys.stderr back to the interpreter defaults so
    subsequent code (pytest, terminal, other tests) no longer writes via
    Qt-backed redirection.
    """
    sys.stdout = sys.__stdout__
    sys.stderr = sys.__stderr__
    _REDIRECTED_STREAMS.clear()


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

    existing_handlers = list(logger.handlers)
    for handler in existing_handlers:
        if handler.get_name() in {"console", "file"}:
            logger.removeHandler(handler)
            handler.close()

    # Format console handler
    date_fmt = "%H:%M:%S"
    formatter = logging.Formatter(fmt, date_fmt, style="{")
    console_handler = logging.StreamHandler(get_redirected_stream("stderr"))
    console_handler.set_name("console")
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Format file handler
    logging_path = Settings().get("log_file_path") or Path.home() / "mne_nodes.log"
    file_handler = logging.FileHandler(logging_path, mode="w", encoding="utf-8")
    file_handler.set_name("file")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Hide filelock logging
    logging.getLogger("filelock").setLevel(logging.INFO)
