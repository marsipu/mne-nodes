"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QTreeView,
    QVBoxLayout,
)

from mne_nodes.gui.widget_models.function_picker_model import FunctionPickerModel


class DraggableTreeView(QTreeView):
    def __init__(self):
        super().__init__()
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)
        self.setSelectionMode(QTreeView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setWordWrap(True)
        self.setHeaderHidden(True)
        self.setUniformRowHeights(False)


class FunctionTree(DraggableTreeView):
    def __init__(self, ct):
        super().__init__()
        model = FunctionPickerModel(ct.function_meta)
        self.setModel(model)
        self.expandAll()


class NodePicker(QDialog):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Node Picker")
        self.setMinimumSize(700, 500)
        layout = QVBoxLayout(self)
        self.functions_view = FunctionTree(controller)
        layout.addWidget(self.functions_view)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)
