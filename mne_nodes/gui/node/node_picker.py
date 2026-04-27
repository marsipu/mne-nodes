"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

from qtpy.QtCore import Qt
from qtpy.QtWidgets import QDockWidget, QTableView, QAbstractItemView

from mne_nodes.gui.models import FunctionPickerModel


class DraggableTableView(QTableView):
    def __init__(self):
        super().__init__()
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)
        self.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setWordWrap(True)
        self.setSortingEnabled(True)
        self.verticalHeader().setVisible(False)


class FunctionTable(DraggableTableView):
    def __init__(self, ct):
        super().__init__()
        model = FunctionPickerModel(ct.function_meta)
        self.setModel(model)


class NodePicker(QDockWidget):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Node Picker")
        self.functions_view = FunctionTable(controller)
        self.setWidget(self.functions_view)
