from contextlib import contextmanager

from qtpy.QtCore import Qt


def toggle_checked_list_model(model, value=1, row=0, column=0):
    value = Qt.CheckState.Checked if value else Qt.CheckState.Unchecked
    model.setData(model.index(row, column), value, Qt.ItemDataRole.CheckStateRole)


@contextmanager
def create_console():
    # Initialize streams and logging
    # Putting stream initialization into a fixture doesn't
    from mne_nodes.pipeline.streams import init_streams
    from mne_nodes.pipeline.streams import init_logging
    from mne_nodes.gui.console import MainConsoleWidget

    init_streams()
    init_logging()
    # Create console widget
    console = MainConsoleWidget()
    try:
        yield console
    finally:
        console.stop_streams()
