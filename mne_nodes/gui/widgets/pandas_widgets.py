"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import itertools

import numpy as np
import pandas as pd
from qtpy import compat
from qtpy.QtCore import QItemSelectionModel, Qt
from qtpy.QtGui import QFont
from qtpy.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTableView,
    QVBoxLayout,
)

from mne_nodes.gui.dialogs import ErrorDialog
from mne_nodes.gui.gui_utils import get_user_input
from mne_nodes.gui.widget_models.pandas_models import BasePandasModel, EditPandasModel
from mne_nodes.gui.widgets.base import Base
from mne_nodes.logger import logger
from mne_nodes.pipeline.exception_handling import get_exception_tuple
from mne_nodes.pipeline.settings import Settings

DATAFRAME_FILE_FILTERS = (
    "Data Files (*.csv *.xlsx *.xls);;"
    "CSV Files (*.csv);;"
    "Excel Files (*.xlsx *.xls);;"
    "All Files (*)"
)

# Tried in order until one decodes the file without a UnicodeDecodeError.
_CSV_ENCODINGS = ("utf-8", "utf-8-sig", "cp1252", "latin1")


def read_dataframe_file(path):
    """Read a DataFrame from a csv or excel file, raising on failure."""
    if path.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(path)

    last_error = None
    for encoding in _CSV_ENCODINGS:
        try:
            return pd.read_csv(path, sep=None, engine="python", encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
    raise ValueError(
        f"Could not decode {path} with any of {_CSV_ENCODINGS}. Last error: {last_error}"
    )


class BasePandasTable(Base):
    """The Base-Class for a table from a pandas DataFrame.

    Parameters
    ----------
    model
        The model for the pandas DataFrame.
    view
        The view for the pandas DataFrame.
    title : str | None
        An optional title.
    """

    def __init__(
        self,
        model,
        view,
        parent=None,
        title=None,
        resize_rows=False,
        resize_columns=False,
    ):
        super().__init__(model=model, view=view, parent=parent, title=title)

        if resize_rows:
            model.layoutChanged.connect(self.view.resizeRowsToContents)
            model.layoutChanged.emit()
        if resize_columns:
            model.layoutChanged.connect(self.view.resizeColumnsToContents)
            model.layoutChanged.emit()

    def get_rowcol_by_index(self, index, data_list):
        """Get the data at index and the row and column of this data.

        Parameters
        ----------
        index : QModelIndex
            The index to get data, row and column for.
        data_list :
            The list in which the information about
             data, rows and columns is stored.
        Notes
        -----
        Because this function is supposed to be called consecutively,
        the information is stored in an existing list (data_list)
        """
        data = self.model.getData(index)
        row = self.model.headerData(
            index.row(),
            orientation=Qt.Orientation.Vertical,
            role=Qt.ItemDataRole.DisplayRole,
        )
        column = self.model.headerData(
            index.column(),
            orientation=Qt.Orientation.Horizontal,
            role=Qt.ItemDataRole.DisplayRole,
        )

        data_list.append((data, row, column))

    def get_current(self):
        current_list = []
        self.get_rowcol_by_index(self.view.currentIndex(), current_list)

        return current_list

    def _current_changed(self, current_idx, previous_idx):
        current_list = []
        previous_list = []

        self.get_rowcol_by_index(current_idx, current_list)
        self.get_rowcol_by_index(previous_idx, previous_list)

        self.currentChanged.emit(current_list, previous_list)

        logger.debug(f"Current changed from {previous_list} to {current_list}")

    def get_selected(self):
        # Somehow, the indexes got from selectionChanged
        # don't appear to be right (maybe some issue with QItemSelection?).
        selection_list = []
        for idx in self.view.selectedIndexes():
            self.get_rowcol_by_index(idx, selection_list)

        return selection_list

    def _selection_changed(self):
        selection_list = self.get_selected()
        self.selectionChanged.emit(selection_list)

        logger.debug(f"Selection changed to {selection_list}")

    def select(self, values=None, rows=None, columns=None, clear_selection=True):
        """Select items in Pandas DataFrame by value or select complete
        rows/columns.

        Parameters
        ----------
        values: list | None
            Names of values in DataFrame.
        rows: list | None
            Names of rows(index).
        columns: list | None
            Names of columns.
        clear_selection: bool | None
            Set True if you want to clear the selection before selecting.
        """
        indexes = []
        # Get indexes for matching items in pd_data
        # (even if there are multiple matches)
        if values:
            for value in values:
                row, column = np.nonzero((self.model._data == value).values)
                indexes.extend(zip(row, column))

        # Select complete rows
        if rows:
            # Convert names into indexes
            row_idxs = [list(self.model._data.index).index(row) for row in rows]
            n_cols = len(self.model._data.columns)
            for row in row_idxs:
                indexes.extend(zip(itertools.repeat(row, n_cols), range(n_cols)))

        # Select complete columns
        if columns:
            # Convert names into indexes
            column_idxs = [list(self.model._data.columns).index(col) for col in columns]
            n_rows = len(self.model._data.index)
            for column in column_idxs:
                indexes.extend(zip(range(n_rows), itertools.repeat(column, n_rows)))

        if clear_selection:
            self.view.selectionModel().clearSelection()

        for row, column in indexes:
            index = self.model.createIndex(row, column)
            self.view.selectionModel().select(
                index, QItemSelectionModel.SelectionFlag.Select
            )


class SimplePandasTable(BasePandasTable):
    """A Widget to display a pandas DataFrame.

    Parameters
    ----------
    data : pandas.DataFrame | None
        Input a pandas DataFrame with contents to display
    parent : QWidget | None
        Parent Widget (QWidget or inherited) or None if there is no parent
    title : str | None
        An optional title
    resize_rows : bool
        Set True to resize the rows to contents
    resize_columns : bool
        Set True to resize the columns to contents

    Notes
    -----
    If you change the Reference to data outside of this class,
    give the changed DataFrame to replace_data to update this widget
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
            model=BasePandasModel(data),
            view=QTableView(),
            parent=parent,
            title=title,
            resize_rows=resize_rows,
            resize_columns=resize_columns,
        )


class EditPandasTable(BasePandasTable):
    """A Widget to display and edit a pandas DataFrame.

    Parameters
    ----------
    data : pandas.DataFrame | None
        Input a pandas DataFrame with contents to display.
    ui_buttons : bool
        If to display Buttons or not.
    ui_button_pos: str
        The side on which to show the buttons,
        'right', 'left', 'top' or 'bottom'
    parent : QWidget | None
        Parent Widget (QWidget or inherited) or None if there is no parent.
    title : str | None
        An optional title
    resize_rows : bool
        Set True to resize the rows to contents.
    resize_columns : bool
        Set True to resize the columns to contents.

    Notes
    -----
    If you change the Reference to data outside of this class,
    give the changed DataFrame to replace_data to update this widget
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
            model=EditPandasModel(data),
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
            addr_layout = QHBoxLayout()
            addr_bt = QPushButton("Add Row")
            addr_bt.setSizePolicy(
                QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum
            )
            addr_bt.clicked.connect(self.add_row)
            addr_layout.addWidget(addr_bt)
            self.rows_chkbx = QSpinBox()
            self.rows_chkbx.setMinimum(1)
            addr_layout.addWidget(self.rows_chkbx)
            bt_layout.addLayout(addr_layout)

            addc_layout = QHBoxLayout()
            addc_bt = QPushButton("Add Column")
            addc_bt.setSizePolicy(
                QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum
            )
            addc_bt.clicked.connect(self.add_column)
            addc_layout.addWidget(addc_bt)
            self.cols_chkbx = QSpinBox()
            self.cols_chkbx.setMinimum(1)
            addc_layout.addWidget(self.cols_chkbx)
            bt_layout.addLayout(addc_layout)

            rmr_bt = QPushButton("Remove Row")
            rmr_bt.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
            rmr_bt.clicked.connect(self.remove_row)
            bt_layout.addWidget(rmr_bt)

            rmc_bt = QPushButton("Remove Column")
            rmc_bt.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
            rmc_bt.clicked.connect(self.remove_column)
            bt_layout.addWidget(rmc_bt)

            edit_bt = QPushButton("Edit")
            edit_bt.setSizePolicy(
                QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum
            )
            edit_bt.clicked.connect(self.edit_item)
            bt_layout.addWidget(edit_bt)

            load_bt = QPushButton("Load")
            load_bt.setSizePolicy(
                QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum
            )
            load_bt.clicked.connect(self.load_file)
            bt_layout.addWidget(load_bt)

            editrh_bt = QPushButton("Edit Row-Header")
            editrh_bt.setSizePolicy(
                QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum
            )
            editrh_bt.clicked.connect(self.edit_row_header)
            bt_layout.addWidget(editrh_bt)

            editch_bt = QPushButton("Edit Column-Header")
            editch_bt.setSizePolicy(
                QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum
            )
            editch_bt.clicked.connect(self.edit_col_header)
            bt_layout.addWidget(editch_bt)

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

    def update_data(self):
        """Has to be called, when model._data is rereferenced by for example
        add_row to keep external data updated.

        Returns
        -------
        data : pandas.DataFrame
            The DataFrame of this widget

        Notes
        -----
        You can overwrite this function in a subclass
         to update an objects attribute.
        (e.g. obj.data = self.model._data)
        """

        return self.model._data

    def add_row(self):
        row = self.view.selectionModel().currentIndex().row() + 1
        # Add row at the bottom if nothing is selected
        if row == -1 or len(self.view.selectionModel().selectedIndexes()) == 0:
            row = 0
        self.model.insertRows(row, self.rows_chkbx.value())
        self.update_data()

    def add_column(self):
        column = self.view.selectionModel().currentIndex().column() + 1
        # Add column to the right if nothing is selected
        if column == -1 or len(self.view.selectionModel().selectedIndexes()) == 0:
            column = 0
        self.model.insertColumns(column, self.cols_chkbx.value())
        self.update_data()

    def remove_row(self):
        rows = sorted(
            {ix.row() for ix in self.view.selectionModel().selectedIndexes()},
            reverse=True,
        )
        for row in rows:
            self.model.removeRow(row)
        self.update_data()

    def remove_column(self):
        columns = sorted(
            {ix.column() for ix in self.view.selectionModel().selectedIndexes()},
            reverse=True,
        )
        for column in columns:
            self.model.removeColumn(column)
        self.update_data()

    def edit_item(self):
        self.view.edit(self.view.selectionModel().currentIndex())

    def load_file(self):
        """Load a DataFrame from a csv/xlsx file, replacing the current data."""
        path, _ = compat.getopenfilename(
            self, "Load DataFrame", filters=DATAFRAME_FILE_FILTERS
        )
        if not path:
            return
        try:
            data = read_dataframe_file(path)
        except Exception:  # noqa: BLE001
            ErrorDialog(get_exception_tuple(), self, f"Could not load {path}").open()
            return
        self.replace_data(data)

    def edit_row_header(self):
        row = self.view.selectionModel().currentIndex().row()
        old_value = self.model._data.index[row]
        text = get_user_input(f"Change Header '{old_value}' in row {row} to:", "string")
        if text is not None:
            self.model.setHeaderData(row, Qt.Orientation.Vertical, text)

    def edit_col_header(self):
        column = self.view.selectionModel().currentIndex().column()
        old_value = self.model._data.columns[column]
        text = get_user_input(
            f"Change Header '{old_value}' in column {column} to:", "string"
        )
        if text is not None:
            self.model.setHeaderData(column, Qt.Orientation.Horizontal, text)
