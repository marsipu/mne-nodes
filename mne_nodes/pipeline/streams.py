"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import io
import sys

from qtpy.QtCore import QObject, Signal


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
