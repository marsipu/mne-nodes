"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

from qtpy.QtCore import Qt
from qtpy.QtWidgets import QDockWidget, QTabWidget, QTableView, QAbstractItemView

from mne_nodes.gui.models import FunctionPickerModel, InputPickerModel


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
        model = FunctionPickerModel(ct.function_metas)
        self.setModel(model)


class InputTable(DraggableTableView):
    def __init__(self, ct):
        super().__init__()
        model = InputPickerModel(ct.inputs)
        self.setModel(model)


class NodePicker(QDockWidget):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.ct = controller
        self.tab_widget = QTabWidget()
        self.setWindowTitle("Node Picker")
        self.setWidget(self.tab_widget)

        # Build tabs
        self._init_functions_tab()
        self._init_inputs_tab()

    def _init_functions_tab(self):
        self.functions_view = FunctionTable(self.ct)
        self.tab_widget.addTab(self.functions_view, "Functions")

    def _init_inputs_tab(self):
        self.inputs_view = InputTable(self.ct)
        self.tab_widget.addTab(self.inputs_view, "Inputs")
