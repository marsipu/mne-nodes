"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

from __future__ import annotations

import sys

import pytest

from mne_nodes.gui.console import ConsoleWidget
from mne_nodes.pipeline.data_import import import_dataset
from mne_nodes.pipeline.execution import ProcessDialog, Process


def test_process(qtbot):
    console = ConsoleWidget()
    qtbot.addWidget(console)
    console.show()
    process = Process(console=console, self_destruct=False)
    process.start(
        sys.executable,
        ["-c", "import sys; print('TEST_OUT'); print('TEST_ERR', file=sys.stderr)"],
    )
    qtbot.wait(100)
    console_text = console.toPlainText()
    assert "TEST_OUT" in console_text, "Stdout not captured in console"
    assert "TEST_ERR" in console_text, "Stderr not captured in console"


@pytest.mark.timeout(10)
def test_main_window_process(qtbot, main_window, controller, tmp_path):
    """Test launching a process through Controller/MainWindow integration.

    Uses a trivial Python one-shot command that writes to stdout &
    stderr.
    """
    console = main_window.console_dock.add_process()
    process = Process(console=console, self_destruct=True)
    process.start(
        sys.executable,
        ["-c", "import sys; print('TEST_OUT'); print('TEST_ERR', file=sys.stderr)"],
    )
    qtbot.wait(100)
    console_text = process.console.toPlainText()
    assert "TEST_OUT" in console_text, "Stdout not captured in console"
    assert "TEST_ERR" in console_text, "Stderr not captured in console"


@pytest.mark.timeout(10)
def test_process_dialog(qtbot):
    """Test the ProcessDialog execution.

    Ensures dialog execution finishes, output is captured, and
    controller stores process.
    """
    py_snippet = "import sys; print('DIALOG_OUT'); print('DIALOG_ERR', file=sys.stderr)"
    commands = [(sys.executable, ["-c", py_snippet])]

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

    # Let console flush
    qtbot.wait(100)
    console_text = dialog.console.toPlainText()
    assert "DIALOG_OUT" in console_text, "Dialog stdout missing"
    assert "DIALOG_ERR" in console_text, "Dialog stderr missing"


def test_simple_pipeline(qtbot, main_window, controller):
    # Import testing dataset (controller fixtures should be identical to main_window.controller)
    # ToDo: Make this test work
    import_dataset(controller, "testing")
    main_window.show()
    qtbot.wait(10000)
