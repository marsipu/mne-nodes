"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

from contextlib import contextmanager

from qtpy.QtCore import Qt
from mne_nodes.pipeline.streams import init_streams
from mne_nodes.pipeline.streams import init_logging
from mne_nodes.gui.console import MainConsoleWidget, ConsoleWidget


def toggle_checked_list_model(model, value=1, row=0, column=0):
    value = Qt.CheckState.Checked if value else Qt.CheckState.Unchecked
    model.setData(model.index(row, column), value, Qt.ItemDataRole.CheckStateRole)


@contextmanager
def create_console(qtbot, main_std=True):
    # Initialize streams and logging
    # Putting stream initialization into a fixture doesn't initialize the streams

    if main_std:
        init_streams()
        init_logging()
        # Create console widget
        console = MainConsoleWidget()
    else:
        console = ConsoleWidget()
    qtbot.addWidget(console)
    try:
        yield console
    finally:
        console.stop_streams()
