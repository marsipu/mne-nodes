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

from mne_nodes.gui.console import ConsoleWidget
from mne_nodes.pipeline.execution import Process
from mne_nodes.gui.run_widgets import ProcessDialog, WorkerDialog


def _wait_for_console_output(qtbot, get_text, expected_substrings, timeout_s=5.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        text = get_text()
        if all(s in text for s in expected_substrings):
            return text
        qtbot.wait(50)
    return get_text()


def test_process(qtbot):
    console = ConsoleWidget()
    qtbot.addWidget(console)
    console.show()
    process = Process(console=console, self_destruct=False)
    process.start(
        sys.executable,
        [
            "-u",
            "-c",
            "import sys; print('TEST_OUT'); print('TEST_ERR', file=sys.stderr)",
        ],
    )
    console_text = _wait_for_console_output(
        qtbot, console.toPlainText, ["TEST_OUT", "TEST_ERR"]
    )
    assert "TEST_OUT" in console_text, "Stdout not captured in console"
    assert "TEST_ERR" in console_text, "Stderr not captured in console"


@pytest.mark.timeout(10)
def test_main_window_process(qtbot, main_window, ct, tmp_path):
    """Test launching a process through Controller/MainWindow integration.

    Uses a trivial Python one-shot command that writes to stdout &
    stderr.
    """
    program = sys.executable
    args = [
        "-u",
        "-c",
        "import sys; print('TEST_OUT'); print('TEST_ERR', file=sys.stderr)",
    ]
    main_window.console_dock.start_process(program, args)
    console_text = _wait_for_console_output(
        qtbot,
        lambda: main_window.console_dock.processes[0].console.toPlainText(),
        ["TEST_OUT", "TEST_ERR"],
    )
    assert "TEST_OUT" in console_text, "Stdout not captured in console"
    assert "TEST_ERR" in console_text, "Stderr not captured in console"


@pytest.mark.timeout(10)
def test_process_dialog(qtbot):
    """Test the ProcessDialog execution.

    Ensures dialog execution finishes, output is captured, and
    controller stores process.
    """
    py_snippet = "import sys; print('DIALOG_OUT'); print('DIALOG_ERR', file=sys.stderr)"
    commands = [(sys.executable, ["-u", "-c", py_snippet])]

    dialog = ProcessDialog(
        parent=None,
        commands=commands,
        show_buttons=False,
        show_console=True,
        close_directly=False,
        blocking=False,
    )
    qtbot.addWidget(dialog)
    # Wait for completion
    with qtbot.waitSignal(dialog.process.finished, timeout=5000):
        pass

    console_text = _wait_for_console_output(
        qtbot, dialog.console.toPlainText, ["DIALOG_OUT", "DIALOG_ERR"]
    )
    assert "DIALOG_OUT" in console_text, "Dialog stdout missing"
    assert "DIALOG_ERR" in console_text, "Dialog stderr missing"


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
