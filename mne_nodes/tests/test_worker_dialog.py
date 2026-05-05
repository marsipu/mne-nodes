"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import sys
import time

from qtpy.QtCore import Qt

from mne_nodes.pipeline.streams import init_streams
from mne_nodes.gui.run_widgets import WorkerDialog


def test_worker_dialog_executes_with_kwargs_and_shows_console(qtbot):
    """Ensure WorkerDialog runs function with kwargs and shows stdout/stderr.

    The test:
    - Redirects sys.stdout/sys.stderr into Qt signals (init_streams)
    - Starts a WorkerDialog with a function that prints to stdout and stderr
      and returns a value based on provided kwargs
    - Waits for the worker to finish
    - Verifies that both stdout and stderr texts appear in the dialog console
    - Clicks close and verifies the emitted return value via thread_finished
    """
    # Ensure stdout/stderr are hooked into Qt signals for the console widget
    init_streams()

    # Test function that uses kwargs, writes to both stdout and stderr, and returns a value
    def work_func(x, y, worker_signals=None):
        # Small delay so the dialog can finish initializing its console connections
        time.sleep(0.15)
        print(f"OUT: {x}+{y}={x + y}")
        print(f"ERR: {x * y}", file=sys.stderr)
        # Optionally exercise progress signals (not strictly required for this test)
        if worker_signals is not None:
            worker_signals.pgbar_max.emit(2)
            worker_signals.pgbar_text.emit("Working...")
            worker_signals.pgbar_n.emit(1)
            worker_signals.pgbar_n.emit(2)
        return x + y

    # Create the dialog; keep it open after finishing so we can inspect the console
    dlg = WorkerDialog(
        parent=None,
        function=work_func,
        show_buttons=True,
        show_console=True,
        close_directly=False,
        blocking=False,
        x=2,
        y=3,
    )
    qtbot.addWidget(dlg)

    # Wait for the worker to finish
    deadline = time.monotonic() + 5.0
    while not dlg.is_finished and time.monotonic() < deadline:
        qtbot.wait(20)
    assert dlg.is_finished, "Worker did not finish in time"

    # Wait for console text to appear (stream worker flush is async)
    out_seen = False
    err_seen = False
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and not (out_seen and err_seen):
        text = dlg.console_output.toPlainText()
        out_seen = out_seen or ("OUT: 2+3=5" in text)
        err_seen = err_seen or ("ERR: 6" in text)
        if out_seen and err_seen:
            break
        qtbot.wait(50)
    assert out_seen, "Expected stdout text not found in console"
    assert err_seen, "Expected stderr text not found in console"

    # Close the dialog and verify the emitted return value
    with qtbot.waitSignal(dlg.thread_finished, timeout=2000) as finished:
        qtbot.mouseClick(dlg.close_bt, Qt.MouseButton.LeftButton)
    assert finished.args[0] == 5
