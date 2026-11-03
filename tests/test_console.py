"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import sys
import time
import traceback
from pathlib import Path

import pytest
import tqdm
from qtpy.QtCore import QProcess

from mne_nodes.backend.execution import Process
from tests._test_utils import create_console


def test_console_dock_reports_process_start(main_window, qtbot, monkeypatch):
    """Tour feedback is emitted on process startup after the console opens."""
    dock = main_window.console_dock

    def test_process(**kwargs):
        return Process(**{**kwargs, "self_destruct": False})

    monkeypatch.setattr("mne_nodes.gui.console.Process", test_process)
    main_window.show()
    dock.hide()
    with qtbot.waitSignal(dock.process_started, timeout=5000):
        dock.start_process(sys.executable, ["-c", "pass"])
    assert dock.isVisible()
    assert dock.tab_widget.count() == 1
    process = dock.processes[0]
    qtbot.waitUntil(
        lambda: process.state() == QProcess.ProcessState.NotRunning, timeout=5000
    )
    assert process.exitCode() == 0
    dock._close_process(0)


def test_console_stream(qtbot):
    """Bytes and text reach the console; massive output does not crash it."""

    with create_console(qtbot, main_std=False) as console:
        wait_time = console.stream_worker.flush_s * 1000 * 2
        console.push_stdout(b"Hello from bytes\n")
        console.push_stdout("and text\n")
        console.push_stderr(b"and Error from bytes\n")
        console.push_stderr("and Error text!\n")
        qtbot.wait(wait_time)
        text = console.toPlainText()
        assert "Hello from bytes" in text
        assert "and text" in text
        assert "and Error from bytes" in text
        assert "and Error text!" in text

        large_chunk = "X" * 10000
        for _ in range(50):
            console.push_stdout(large_chunk + "\n")
        qtbot.wait(2000)
        assert len(console.toPlainText()) > 0


def test_formatting(qtbot):
    # Simplified expected test to account for platform differences
    expected_text = [
        "Test1",
        "20/20",
        "Traceback (most recent call last):",
        "in test_formatting",
        "raise RuntimeError",
        "RuntimeError: Test-Error",
        "Test2",
    ]
    with create_console(qtbot) as console:
        print("Test1")
        for i in tqdm.tqdm(range(20), desc="Progress"):
            time.sleep(0.1)
        try:
            raise RuntimeError("Test-Error")
        except RuntimeError:
            traceback.print_exc()
        print("Test2")
        # Check console content
        qtbot.wait(100)
        text = console.toPlainText()
        for actual, expected in zip(text.splitlines(), expected_text):
            assert expected in actual, f"Expected '{expected}', got '{actual}'"


# Skip until #47 is worked on
@pytest.mark.skip(reason="temporarily disabled")
def test_process_formatting(qtbot, tmp_path):
    """Test that process output formatting works in the console."""

    with create_console(qtbot, main_std=False) as console:
        test_file = Path(__file__).parent / "_test_process.py"
        expected_text = [
            "Test1",
            "10/10",
            "Traceback (most recent call last):",
            "raise RuntimeError",
            "RuntimeError: Test-Error",
            "Test2",
        ]
        process = Process(console=console, self_destruct=False)
        process.start(sys.executable, [str(test_file)])
        # Check console content
        qtbot.wait(1000)
        actual = console.toPlainText()
        for expected in expected_text:
            assert expected in actual, f"Expected '{expected}' not in '{actual}'"
