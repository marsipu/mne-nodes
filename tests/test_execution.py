"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

from __future__ import annotations

import sys
import time

import pytest
from qtpy.QtCore import Qt

from mne_nodes.backend.execution import Process
from mne_nodes.gui.console import ConsoleWidget
from mne_nodes.gui.dialogs.run_dialogs import ProcessDialog, WorkerDialog


def _wait_for_console_output(qtbot, get_text, expected_substrings, timeout_s=5.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        text = get_text()
        if all(s in text for s in expected_substrings):
            return text
        qtbot.wait(50)
    return get_text()


def test_process(qtbot):
    """Unbuffered stdout/stderr reach the console while the process still runs."""
    console = ConsoleWidget()
    qtbot.addWidget(console)
    console.show()
    process = Process(console=console, self_destruct=False)
    assert process.processEnvironment().value("MNE_NODES_GUI_CONSOLE") == "1"
    process.start(
        sys.executable,
        [
            "-c",
            (
                "import sys, time\n"
                "from mne_nodes.backend import process_log as log\n"
                "log.pipeline_start()\n"
                "with log.function('step'):\n"
                "    print('TEST_OUT')\n"
                "    print('TEST_ERR', file=sys.stderr)\n"
                "    time.sleep(30)\n"
            ),
        ],
    )
    console_text = _wait_for_console_output(
        qtbot, console.toPlainText, ["TEST_OUT", "TEST_ERR"], timeout_s=15
    )
    assert process.state() != Process.ProcessState.NotRunning
    process.kill()
    process.waitForFinished(5000)
    assert "TEST_OUT" in console_text, "Stdout not captured in console"
    assert "TEST_ERR" in console_text, "Stderr not captured in console"
    # Function output is indented inside the function's frame.
    assert "▶ step" in console_text
    assert "│ TEST_OUT" in console_text
    assert "\x1b" not in console_text


def test_process_dialog_waits_for_all_commands(qtbot):
    """Only the final command completes the dialog and sets its exit code."""
    dialog = ProcessDialog(
        commands=[
            (sys.executable, "-c", "pass"),
            (sys.executable, "-c", "import sys; sys.exit(7)"),
        ],
        blocking=False,
        show_console=False,
    )
    qtbot.addWidget(dialog)
    completions = []
    dialog.process.finished.connect(
        lambda code, status: completions.append((code, dialog.is_finished))
    )
    with qtbot.waitSignal(dialog.process.destroyed, timeout=5000):
        assert not dialog.is_finished
    assert completions == [(0, False), (7, True)]
    assert dialog.exit_code == 7


@pytest.mark.timeout(10)
def test_worker_dialog(qtbot):
    """Test WorkerDialog execution and emitted return value on close."""

    def work_func(x, y, worker_signals=None):
        if worker_signals is not None:
            worker_signals.pgbar_max.emit(1)
            worker_signals.pgbar_text.emit("Working")
            worker_signals.pgbar_n.emit(1)
        return x + y

    dialog = WorkerDialog(
        parent=None,
        function=work_func,
        show_buttons=True,
        show_console=False,
        close_directly=False,
        blocking=False,
        x=2,
        y=3,
    )
    qtbot.addWidget(dialog)

    deadline = time.monotonic() + 5.0
    while not dialog.is_finished and time.monotonic() < deadline:
        qtbot.wait(20)
    assert dialog.is_finished, "WorkerDialog did not finish in time"

    with qtbot.waitSignal(dialog.thread_finished, timeout=2000) as finished:
        qtbot.mouseClick(dialog.close_bt, Qt.MouseButton.LeftButton)
    assert finished.args[0] == 5
