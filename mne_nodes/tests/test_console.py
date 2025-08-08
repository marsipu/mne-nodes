"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import logging
import os

import pytest

from mne_nodes.__main__ import init_streams, init_logging
from mne_nodes.gui.console import ConsoleWidget


def test_logging(qtbot):
    """Test streaming and logging to GUI-Console."""
    # Enable debugging
    os.environ["MNENODES_DEBUG"] = "true"

    init_streams()
    init_logging()

    console = ConsoleWidget()
    qtbot.addWidget(console)

    wait_time = console.buffer_time * 2

    print("Print-Test")
    qtbot.wait(wait_time)
    assert "Print-Test" in console.toPlainText()

    with pytest.raises(RuntimeError):
        raise RuntimeError("Test-Error")

    qtbot.wait(wait_time)
    assert "Test-Error" in console.toPlainText()

    logging.info("Logging-Test")
    qtbot.wait(wait_time)
    assert "[INFO] Logging-Test" in console.toPlainText()
