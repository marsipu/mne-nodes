"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import logging

from qtpy.QtCore import QItemSelectionModel, Signal
from qtpy.QtGui import QFont
from qtpy.QtWidgets import QAbstractItemView, QLabel, QVBoxLayout, QWidget

from mne_nodes.pipeline.settings import Settings


class Base(QWidget):
    currentChanged = Signal(object, object)
    selectionChanged = Signal(object)
    dataChanged = Signal(object, object)

    def __init__(self, model, view, parent, title):
        if parent:
            super().__init__(parent)
        else:
            super().__init__()
        self.title = title

        self.model = model
        self.view = view
        self.view.setModel(self.model)

        # Connect to custom Selection-Signal
        self.view.selectionModel().currentChanged.connect(self._current_changed)
        self.view.selectionModel().selectionChanged.connect(self._selection_changed)
        self.model.dataChanged.connect(self._data_changed)
        # Also send signal when rows are removed/added
        self.model.rowsInserted.connect(self._data_changed)
        self.model.rowsRemoved.connect(self._data_changed)

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        if self.title:
            title_label = QLabel(self.title)
            if len(self.title) <= 12:
                title_label.setFont(QFont(Settings().get("app_font"), 14))
            else:
                title_label.setFont(QFont(Settings().get("app_font"), 12))
            layout.addWidget(title_label)

        layout.addWidget(self.view)
        self.setLayout(layout)

    def get_current(self):
        try:
            current = self.model.getData(self.view.currentIndex())
        except (KeyError, IndexError):
            current = None

        return current

    def _current_changed(self, current_idx, previous_idx):
        current = self.model.getData(current_idx)
        # ToDo: For ListWidget after removal,
        #  there is a bug when previous_idx is too high
        previous = self.model.getData(previous_idx)

        self.currentChanged.emit(current, previous)

        logging.debug(f"Current changed from {previous} to {current}")

    def get_selected(self):
        try:
            selected = [self.model.getData(idx) for idx in self.view.selectedIndexes()]
        except (KeyError, IndexError):
            selected = []

        return selected

    def _selection_changed(self):
        # Although the SelectionChanged-Signal sends
        # selected/deselected indexes, I don't use them here, because they
        # don't seem represent the selection.
        selected = self.get_selected()

        self.selectionChanged.emit(selected)

        logging.debug(f"Selection changed to {selected}")

    def _data_changed(self, index, _):
        data = self.model.getData(index)

        self.dataChanged.emit(data, index)
        logging.debug(f"{data} changed at {index}")

    def content_changed(self):
        """Informs ModelView about external change made in data."""
        self.model.layoutChanged.emit()

    def replace_data(self, new_data):
        """Replaces model._data with new_data."""
        self.model._data = new_data
        self.content_changed()


class BaseList(Base):
    def __init__(self, model, view, extended_selection=False, parent=None, title=None):
        super().__init__(model, view, parent, title)

        if extended_selection:
            self.view.setSelectionMode(
                QAbstractItemView.SelectionMode.ExtendedSelection
            )

    def select(self, values, clear_selection=True):
        indices = [i for i, x in enumerate(self.model._data) if x in values]

        if clear_selection:
            self.view.selectionModel().clearSelection()

        for idx in indices:
            index = self.model.createIndex(idx, 0)
            self.view.selectionModel().select(
                index, QItemSelectionModel.SelectionFlag.Select
            )
