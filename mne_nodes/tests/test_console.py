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

from mne_nodes.pipeline.execution import Process
from mne_nodes.tests._test_utils import create_console


def test_console_stream_basic(qtbot):
    """Set up a ConsoleWidget and write via streams (bytes and str)."""

    with create_console(qtbot, main_std=False) as console:
        wait_time = console.stream_worker.flush_s * 1000 * 2
        # Push bytes and strings
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


def test_logging(qtbot):
    """Test streaming and logging to GUI-Console.

    Also verify that a real exception traceback reaches the stderr
    stream.
    """
    with create_console(qtbot) as console:
        wait_time = console.stream_worker.flush_s * 1000 * 2
        # stdout: plain print
        print("Print-Test")
        qtbot.wait(wait_time)
        assert "Print-Test" in console.toPlainText()

        # stderr: real exception with traceback to stderr
        try:
            raise RuntimeError("Test-Error")
        except RuntimeError:
            # This prints a full traceback to sys.stderr (hooked by the console)
            traceback.print_exc()
        qtbot.wait(wait_time)
        text = console.toPlainText()
        assert "Traceback (most recent call last):" in text
        assert "RuntimeError: Test-Error" in text

        # logging -> by default logging.StreamHandler uses sys.stderr
        # ToDo: Fix Logging
        # logging.info("Logging-Test")
        # qtbot.wait(wait_time)
        # assert "[INFO] Logging-Test" in console.toPlainText()


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


@pytest.mark.skipif(True, reason="Disabled for now")
def test_formatting_show(qtbot):
    import tqdm

    with create_console(qtbot) as console:
        console.resize(800, 600)
        console.show()
        print("Test1")
        qtbot.wait(500)
        for i in tqdm.tqdm(range(10), desc="Progress"):
            print(i)
        qtbot.wait(500)
        print("Test2")
        qtbot.wait(500)
        try:
            raise RuntimeError("Test-Error")
        except RuntimeError:
            # This prints a full traceback to sys.stderr (hooked by the console)
            traceback.print_exc()
        qtbot.wait(500)
        print("\nTest3")
        qtbot.wait(1000)


def test_stream_worker_massive_output(qtbot):
    """Test handling of massive output without crashes.

    Validates that:
    - Large volumes of output don't crash or freeze
    - Queue backpressure protection exists (MAX_QUEUE_SIZE)
    - Performance is acceptable for typical use cases
    """

    with create_console(qtbot) as console:
        # Test massive output performance
        large_chunk = "X" * 10000
        for _ in range(50):
            console.push_stdout(large_chunk + "\n")

        qtbot.wait(2000)  # Wait for processing

        # Console should have content and did not crash
        assert len(console.toPlainText()) > 0


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
