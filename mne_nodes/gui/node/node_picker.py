"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

from PySide6.QtCore import QMimeData
from PySide6.QtGui import QPixmap, QPainter, QDrag
from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QDockWidget,
    QTabWidget,
    QTableView,
    QAbstractItemView,
    QHeaderView,
)

from mne_nodes.gui.models import FunctionPickerModel, InputPickerModel


class DraggableTableHeader(QHeaderView):
    def __init__(self, parent):
        super().__init__(Qt.Orientation.Vertical, parent=parent)

    def mousePressEvent(self, event):
        self._pressed_index = self.logicalIndexAt(event.pos())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self._pressed_index is not None:
            drag = QDrag(self)
            mime = QMimeData()
            mime.setText(f"Row {self._pressed_index}")
            drag.setMimeData(mime)

            # Optional: visual preview
            pixmap = QPixmap(80, 30)
            pixmap.fill(Qt.lightGray)
            painter = QPainter(pixmap)
            painter.drawText(
                pixmap.rect(), Qt.AlignCenter, f"Row {self._pressed_index}"
            )
            painter.end()
            drag.setPixmap(pixmap)
            drag.setHotSpot(event.pos())

            drag.exec_(Qt.CopyAction)
            self._pressed_index = None
        else:
            super().mouseMoveEvent(event)


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
        self.horizontalHeader().setStretchLastSection(True)
        # ToDo Next: Just don't show the vertical header but show names instead
        header = DraggableTableHeader(self)
        self.setVerticalHeader(header)


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
