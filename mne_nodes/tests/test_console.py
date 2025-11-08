"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import logging
import traceback


def test_console_stream_basic(qtbot):
    """Set up a ConsoleWidget and write via streams (bytes and str)."""
    from mne_nodes.gui.console import ConsoleWidget

    console = ConsoleWidget()
    qtbot.addWidget(console)
    try:
        # Faster flush for test speed
        console.add_stream("stdout", flush_interval_ms=20)

        # Push bytes and strings
        console.get_stream("stdout").push(b"Hello from bytes\n")
        console.get_stream("stdout").push(" and text!\n")

        qtbot.wait(100)
        text = console.toPlainText()
        assert "Hello from bytes" in text
        assert "and text!" in text
    finally:
        console.stop_streams()


def test_logging(qtbot):
    """Test streaming and logging to GUI-Console.

    Also verify that a real exception traceback reaches the stderr
    stream.
    """
    from mne_nodes.gui.console import MainConsoleWidget
    from mne_nodes.pipeline.streams import init_streams, init_logging

    # Initialize streams and logging
    # Putting stream initialization into a fixture doesn't
    init_streams()
    init_logging()
    # Create console widget
    console = MainConsoleWidget()
    qtbot.addWidget(console)
    try:
        wait_time = console.buffer_time * 2
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
        logging.info("Logging-Test")
        qtbot.wait(wait_time)
        assert "[INFO] Logging-Test" in console.toPlainText()
    finally:
        # Stop streams to avoid blocking the test after finish
        console.stop_streams()
