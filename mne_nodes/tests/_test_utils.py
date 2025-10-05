from mne_nodes.qt_compat import CHECKED, UNCHECKED
from qtpy.QtCore import Qt


def toggle_checked_list_model(model, value=1, row=0, column=0):
    value = CHECKED if value else UNCHECKED
    model.setData(model.index(row, column), value, Qt.CheckStateRole)
