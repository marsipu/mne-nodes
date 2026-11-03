"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import sys
import time
import traceback
from io import StringIO
from pathlib import Path

import pytest
import tqdm
from qtpy.QtCore import QProcess, QTimer
from rich.console import Console
from rich.progress import Progress

from mne_nodes.backend.execution import Process
from mne_nodes.logger import logger
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

        output = StringIO()
        rich_console = Console(file=output, force_terminal=True)
        rich_console.print("[bold green]Rich output[/bold green]")
        console.push_stdout(output.getvalue())
        console.push_stdout(b"\x1b[3")
        console.push_stdout(b"2mSplit \xc3")
        console.push_stderr("Independent stream\n")
        console.push_stdout(b"\xa9 ANSI\x1b[0m\n")
        console.push_stdout("\x1b]8;id=1;https://example.com")
        console.push_stdout("\x1b")
        console.push_stdout("\\Link\x1b]8;;\x1b\\\n")
        console.push_stdout("\rCRLF progress 100%\r")
        console.push_stdout("\n")
        console.push_stdout("<b>literal &lt; & text</b>\n  indented\n")
        qtbot.waitUntil(lambda: "indented" in console.toPlainText())
        text = console.toPlainText()
        assert "Rich output" in text
        assert "Split Independent stream\né ANSI" in text
        assert "<b>literal &lt; & text</b>" in text
        assert "Link\n" in text
        assert "https://example.com" not in text
        assert "CRLF progress 100%\n" in text
        assert "\x1b" not in text

        console.push_stdout(
            "\x1b[31mPrior red\n\r\x1b[0m10%\r100% reset-state\n"
        )
        qtbot.waitUntil(lambda: "100% reset-state" in console.toPlainText())
        assert console.stream_worker._ansi_decoders["stdout"].style.color is None

        console.push_stdout("Initial 0%")
        qtbot.waitUntil(lambda: "Initial 0%" in console.toPlainText())
        console.push_stdout("\rFinal 100%\n")
        qtbot.waitUntil(lambda: "Final 100%" in console.toPlainText())
        text = console.toPlainText()
        assert "Initial 0%" not in text
        assert text.count("Final 100%") == 1

        ticks = []
        timer = QTimer(console)
        timer.timeout.connect(lambda: ticks.append(True))
        timer.start(10)
        large_chunk = "\x1b[32m" + "X" * 10000 + "\x1b[0m"
        for _ in range(50):
            console.push_stdout(large_chunk + "\n")
        console.push_stdout("Burst complete\n")
        qtbot.waitUntil(
            lambda: "Burst complete" in console.toPlainText(), timeout=10000
        )
        timer.stop()
        assert ticks
        assert console.toPlainText().count("X") == 500000
        assert console.stream_worker._dropped_count == 0


def test_formatting(qtbot, monkeypatch, settings):
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
        logger.warning("Pipeline progress: [literal markup] <file> & data")
        qtbot.waitUntil(lambda: "Pipeline progress:" in console.toPlainText())
        assert "[literal markup] <file> & data" in console.toPlainText()
        log_text = settings.get("log_file_path").read_text(encoding="utf-8")
        assert "[WARNING] Pipeline progress:" in log_text
        assert "\x1b" not in log_text

        monkeypatch.setenv("TERM", "xterm-256color")
        output = StringIO()
        with Progress(
            console=Console(file=output, force_terminal=True, width=80),
            auto_refresh=False,
            redirect_stdout=False,
            redirect_stderr=False,
        ) as progress:
            task = progress.add_task("Rich pipeline", total=2)
            progress.update(task, advance=1, refresh=True)
            progress.update(task, advance=1, refresh=True)
        ansi = output.getvalue()
        for start in range(0, len(ansi), 23):
            console.push_stdout(ansi[start : start + 23])
        console.push_stdout("After Rich progress\n")
        qtbot.waitUntil(lambda: "After Rich progress" in console.toPlainText())
        text = console.toPlainText()
        assert text.count("Rich pipeline") == 1
        assert "100%" in text
        assert "\x1b" not in text


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
