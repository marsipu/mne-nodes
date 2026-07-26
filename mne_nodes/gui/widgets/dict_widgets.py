"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import logging

from qtpy.QtCore import QItemSelectionModel, Qt
from qtpy.QtGui import QFont
from qtpy.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTableView,
    QVBoxLayout,
)

from mne_nodes.pipeline.settings import Settings
from mne_nodes.gui.widgets.base import Base
from mne_nodes.gui.widget_models.dict_models import BaseDictModel, EditDictModel


class BaseDict(Base):
    def __init__(
        self,
        model,
        view,
        parent=None,
        title=None,
        resize_rows=False,
        resize_columns=False,
    ):
        super().__init__(model, view, parent, title)

        if resize_rows:
            model.layoutChanged.connect(self.view.resizeRowsToContents)
            model.layoutChanged.emit()
        if resize_columns:
            model.layoutChanged.connect(self.view.resizeColumnsToContents)
            model.layoutChanged.emit()

    def get_keyvalue_by_index(self, index):
        """For the given index, make an entry in item_dict with the data at
        index as key and a dict as value defining. if data is key or value and
        refering to the corresponding key/value of data depending on its type.

        Parameters
        ----------
        index: Index in Model
        """

        if index.column() == 0:
            counterpart_idx = index.sibling(index.row(), 1)
            key = self.model.getData(index)
            value = self.model.getData(counterpart_idx)
        else:
            counterpart_idx = index.sibling(index.row(), 0)
            key = self.model.getData(counterpart_idx)
            value = self.model.getData(index)

        return key, value

    def get_current(self):
        return self.get_keyvalue_by_index(self.view.currentIndex())

    def _current_changed(self, current_idx, previous_idx):
        current_data = self.get_keyvalue_by_index(current_idx)
        previous_data = self.get_keyvalue_by_index(previous_idx)

        self.currentChanged.emit(current_data, previous_data)

        logging.debug(f"Current changed from {current_data} to {previous_data}")

    def _selected_keyvalue(self, indexes):
        try:
            return {self.get_keyvalue_by_index(idx) for idx in indexes}
        except TypeError:
            return [self.get_keyvalue_by_index(idx) for idx in indexes]

    def get_selected(self):
        return self._selected_keyvalue(self.view.selectedIndexes())

    def _selection_changed(self):
        selected_data = self.get_selected()

        self.selectionChanged.emit(selected_data)

        logging.debug(f"Selection to {selected_data}")

    def select(self, keys, values, clear_selection=True):
        key_indices = [i for i, x in enumerate(self.model._data.keys()) if x in keys]
        value_indices = [
            i for i, x in enumerate(self.model._data.values()) if x in values
        ]

        if clear_selection:
            self.view.selectionModel().clearSelection()

        for idx in key_indices:
            index = self.model.createIndex(idx, 0)
            self.view.selectionModel().select(
                index, QItemSelectionModel.SelectionFlag.Select
            )

        for idx in value_indices:
            index = self.model.createIndex(idx, 1)
            self.view.selectionModel().select(
                index, QItemSelectionModel.SelectionFlag.Select
            )


class SimpleDict(BaseDict):
    """A Widget to display a Dictionary.

    Parameters
    ----------
    data : dict | None
        Input a pandas DataFrame with contents to display.
    parent : QWidget | None
        Parent Widget (QWidget or inherited) or None if there is no parent.
    title : str | None
        An optional title.
    resize_rows : bool
        Set True to resize the rows to contents.
    resize_columns : bool
        Set True to resize the columns to contents.
    """

    def __init__(
        self,
        data=None,
        parent=None,
        title=None,
        resize_rows=False,
        resize_columns=False,
    ):
        super().__init__(
            model=BaseDictModel(data),
            view=QTableView(),
            parent=parent,
            title=title,
            resize_rows=resize_rows,
            resize_columns=resize_columns,
        )


# ToDo: DataChanged somehow not emitted when row is removed
# ToDo: Bug when removing multiple rows (fix and add tests)


class EditDict(BaseDict):
    """A Widget to display and edit a Dictionary.

    Parameters
    ----------
    data : dict | None
        Input a pandas DataFrame with contents to display.
    ui_buttons : bool
        If to display Buttons or not.
    ui_button_pos: str
        The side on which to show the buttons,
         'right', 'left', 'top' or 'bottom'.
    parent : QWidget | None
        Parent Widget (QWidget or inherited) or None if there is no parent.
    title : str | None
        An optional title.
    resize_rows : bool
        Set True to resize the rows to contents.
    resize_columns : bool
        Set True to resize the columns to contents.
    """

    def __init__(
        self,
        data=None,
        ui_buttons=True,
        ui_button_pos="right",
        parent=None,
        title=None,
        resize_rows=False,
        resize_columns=False,
    ):
        self.ui_buttons = ui_buttons
        self.ui_button_pos = ui_button_pos

        super().__init__(
            model=EditDictModel(data),
            view=QTableView(),
            parent=parent,
            title=title,
            resize_rows=resize_rows,
            resize_columns=resize_columns,
        )

    def init_ui(self):
        if self.ui_button_pos in ["top", "bottom"]:
            layout = QVBoxLayout()
            bt_layout = QHBoxLayout()
        else:
            layout = QHBoxLayout()
            bt_layout = QVBoxLayout()

        if self.ui_buttons:
            addrow_bt = QPushButton("Add")
            addrow_bt.setSizePolicy(
                QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum
            )
            addrow_bt.clicked.connect(self.add_row)
            bt_layout.addWidget(addrow_bt)

            rmrow_bt = QPushButton("Remove")
            rmrow_bt.setSizePolicy(
                QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum
            )
            rmrow_bt.clicked.connect(self.remove_row)
            bt_layout.addWidget(rmrow_bt)

            edit_bt = QPushButton("Edit")
            edit_bt.setSizePolicy(
                QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum
            )
            edit_bt.clicked.connect(self.edit_item)
            bt_layout.addWidget(edit_bt)

            layout.addLayout(bt_layout)

        if self.ui_button_pos in ["top", "left"]:
            layout.addWidget(self.view)
        else:
            layout.insertWidget(0, self.view)

        if self.title:
            super_layout = QVBoxLayout()
            title_label = QLabel(self.title)
            title_label.setFont(QFont(Settings().get("app_font"), 14))
            super_layout.addWidget(title_label, alignment=Qt.AlignmentFlag.AlignHCenter)
            super_layout.addLayout(layout)
            self.setLayout(super_layout)
        else:
            self.setLayout(layout)

    def add_row(self):
        row = self.view.selectionModel().currentIndex().row() + 1
        if row == -1:
            row = 0
        self.model.insertRow(row)

    def remove_row(self):
        row_idxs = {idx.row() for idx in self.view.selectionModel().selectedIndexes()}
        for row_idx in row_idxs:
            self.model.removeRow(row_idx)

    def edit_item(self):
        self.view.edit(self.view.selectionModel().currentIndex())
