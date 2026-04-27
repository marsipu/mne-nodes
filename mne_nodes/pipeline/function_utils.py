"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import gc
import io
import sys

from matplotlib import pyplot as plt
from qtpy.QtCore import QRunnable, Slot, QObject, Signal


class StreamManager:
    def __init__(self, pipe):
        self.pipe_busy = False
        self.stdout_sender = StreamSender(self, "stdout", pipe)
        self.stderr_sender = StreamSender(self, "stderr", pipe)


class StreamSender(io.TextIOBase):
    def __init__(self, manager, kind, pipe):
        super().__init__()
        self.manager = manager
        self.kind = kind
        if kind == "stdout":
            self.original_stream = sys.__stdout__
        else:
            self.original_stream = sys.__stderr__
        self.pipe = pipe

    def write(self, text):
        # Still send output to the command-line
        self.original_stream.write(text)
        # Wait until pipe is free
        while self.manager.pipe_busy:
            pass
        self.manager.pipe_busy = True
        kind = self.kind
        self.pipe.send((text, kind))
        self.manager.pipe_busy = False


class StreamRcvSignals(QObject):
    stdout_received = Signal(str)
    stderr_received = Signal(str)


class StreamReceiver(QRunnable):
    def __init__(self, pipe):
        super().__init__()
        self.pipe = pipe
        self.signals = StreamRcvSignals()

    @Slot()
    def run(self):
        while True:
            try:
                text, kind = self.pipe.recv()
            except EOFError:
                break
            else:
                if kind == "stderr":
                    self.signals.stderr_received.emit(text)
                else:
                    self.signals.stdout_received.emit(text)


def close_all():
    plt.close("all")
    gc.collect()
