"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import itertools
import logging
import re

import numpy as np

from qtpy.QtCore import QItemSelectionModel, QTimer, Signal, Qt
from qtpy.QtGui import QFont, QColor
from qtpy.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListView,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTableView,
    QTreeView,
    QVBoxLayout,
    QWidget,
    QComboBox,
    QMessageBox,
    QStyledItemDelegate,
    QHeaderView,
)

from mne_nodes import _widgets
from mne_nodes.gui.gui_utils import get_user_input
from mne_nodes.gui.models import (
    BaseDictModel,
    BaseListModel,
    BasePandasModel,
    CheckDictEditModel,
    CheckDictModel,
    CheckListModel,
    EditDictModel,
    EditListModel,
    EditPandasModel,
    FileManagementModel,
    ShallowTreeModel,
    TreeModel,
    CheckListProgressModel,
)
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


class SimpleList(BaseList):
    """A basic List-Widget to display the content of a list.

    Parameters
    ----------
    data : list[str] | None
        Input a list with contents to display.
    extended_selection: bool
        Set True, if you want to select more than one item in the list.
    show_index: bool
        Set True if you want to display the list-index in front of each value.
    parent : QWidget | None
        Parent Widget (QWidget or inherited) or None if there is no parent.
    title : str | None
        An optional title.

    Notes
    -----
    If you change the contents of data outside of this class,
    call content_changed to update this widget.
    If you change the reference to data, call the appropriate replace_data.
    """

    def __init__(
        self,
        data=None,
        extended_selection=False,
        show_index=False,
        parent=None,
        title=None,
    ):
        super().__init__(
            model=BaseListModel(data, show_index),
            view=QListView(),
            extended_selection=extended_selection,
            parent=parent,
            title=title,
        )


class EditList(BaseList):
    """An editable List-Widget to display and manipulate the content of a list.

    Parameters
    ----------
    data : list[str] | None
        Input a list with contents to display.
    ui_buttons : bool
        If to display Buttons or not.
    ui_button_pos: str
        The side on which to show the buttons,
         'right', 'left', 'top' or 'bottom'.
    show_index: bool
        Set True if you want to display the list-index in front of each value.
    parent : QWidget | None
        Parent Widget (QWidget or inherited) or None if there is no parent.
    title : str | None
        An optional title.
    model : QAbstractItemModel
        Provide an alternative to EditListModel.

    Notes
    -----
    If you change the contents of the list outside of this class,
     call content_changed to update this widget.
    If you change the reference to data, call replace_data.
    """

    def __init__(
        self,
        data=None,
        ui_buttons=True,
        ui_button_pos="right",
        extended_selection=False,
        show_index=False,
        parent=None,
        title=None,
        model=None,
    ):
        self.ui_buttons = ui_buttons
        self.ui_button_pos = ui_button_pos

        if model is None:
            model = EditListModel(data, show_index=show_index)

        super().__init__(
            model=model,
            view=QListView(),
            extended_selection=extended_selection,
            parent=parent,
            title=title,
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

    # Todo: Add Rows at all possible positions
    def add_row(self):
        row = self.view.selectionModel().currentIndex().row() + 1
        if row == -1:
            row = 0
        self.model.insertRow(row)

    def remove_row(self):
        row_idxs = self.view.selectionModel().selectedRows()
        for row_idx in row_idxs:
            self.model.removeRow(row_idx.row())

    def edit_item(self):
        self.view.edit(self.view.selectionModel().currentIndex())


class CheckList(BaseList):
    """A Widget for a Check-List.

    Parameters
    ----------
    data : list[str] | None
        Input a list with contents to display.
    checked : list[str] | None
        Input a list, which will contain the checked items
        from data (and which intial items will be checked).
    ui_buttons : bool
        If to display Buttons or not.
    one_check : bool
        If only one Item in the CheckList can be checked at the same time.
    show_index: bool
        Set True if you want to display the list-index in front of each value.
    parent : QWidget | None
        Parent Widget (QWidget or inherited) or None if there is no parent.
    title : str | None
        An optional title
    model : QAbstractItemModel
        Provide an alternative to CheckListModel.

    Notes
    -----
    If you change the contents of data outside of this class,
     call content_changed to update this widget.
    If you change the reference to data, call replace_data or replace_checked.
    """

    checkedChanged = Signal(list)

    def __init__(
        self,
        data=None,
        checked=None,
        ui_buttons=True,
        ui_button_pos="right",
        one_check=False,
        show_index=False,
        parent=None,
        title=None,
        model=None,
    ):
        self.ui_buttons = ui_buttons
        self.ui_button_pos = ui_button_pos

        model = model or CheckListModel(data, checked, one_check, show_index)
        super().__init__(
            model=model,
            view=QListView(),
            extended_selection=False,
            parent=parent,
            title=title,
        )

        self.model.dataChanged.connect(self._checked_changed)

    def init_ui(self):
        if self.ui_button_pos in ["top", "bottom"]:
            layout = QVBoxLayout()
            bt_layout = QHBoxLayout()
        else:
            layout = QHBoxLayout()
            bt_layout = QVBoxLayout()

        if self.ui_buttons:
            all_bt = QPushButton("All")
            all_bt.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
            all_bt.clicked.connect(self.select_all)
            bt_layout.addWidget(all_bt)

            clear_bt = QPushButton("Clear")
            clear_bt.setSizePolicy(
                QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum
            )
            clear_bt.clicked.connect(self.clear_all)
            bt_layout.addWidget(clear_bt)

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

    def _checked_changed(self):
        self.checkedChanged.emit(self.model._checked)
        logging.debug(f"Changed values: {self.model._checked}")

    def replace_checked(self, new_checked):
        """Replaces model._checked with new checked list."""
        self.model._checked = new_checked
        self.content_changed()

    def select_all(self):
        """Select all Items while leaving reference to model._checked
        intact."""
        for item in [i for i in self.model._data if i not in self.model._checked]:
            self.model._checked.append(item)
        # Inform Model about changes
        self.content_changed()
        self._checked_changed()

    def clear_all(self):
        """Deselect all Items while leaving reference to model._checked
        intact."""
        self.model._checked.clear()
        # Inform Model about changes
        self.content_changed()
        self._checked_changed()


class CheckDictList(BaseList):
    """A List-Widget to display the items of a list and mark them depending on
    their appearance in check_dict.

    Parameters
    ----------
    data : list[str] | None
        A list with items to display.
    check_dict : dict | None
        A dictionary that may contain items from data as keys.
    show_index: bool
        Set True if you want to display the list-index in front of each value.
    yes_bt: str
        Supply the name for a qt-standard-icon to mark the items existing in
         check_dict.
    no_bt: str
        Supply the name for a qt-standard-icon to mark the items
         not existing in check_dict.
    parent : QWidget | None
        Parent Widget (QWidget or inherited) or None if there is no parent.
    title : str | None
        An optional title.

    Notes
    -----
    If you change the contents of data outside of this class,
     call content_changed to update this widget.
    If you change the reference to data, call replace_data.
    If you change the reference to check_dict, call replace_check_dict.

    Names for QT standard-icons:
    https://doc.qt.io/qt-5/qstyle.html#StandardPixmap-enum
    """

    def __init__(
        self,
        data=None,
        check_dict=None,
        extended_selection=False,
        show_index=False,
        yes_bt=None,
        no_bt=None,
        parent=None,
        title=None,
    ):
        super().__init__(
            model=CheckDictModel(data, check_dict, show_index, yes_bt, no_bt),
            view=QListView(),
            extended_selection=extended_selection,
            parent=parent,
            title=title,
        )

    def replace_check_dict(self, new_check_dict=None):
        """Replaces model.check_dict with new check_dict."""
        if new_check_dict:
            self.model._check_dict = new_check_dict
        self.content_changed()


class CheckDictEditList(EditList):
    """A List-Widget to display the items of a list and mark them depending of
    their appearance in check_dict.

    Parameters
    ----------
    data : list[str] | None
        A list with items to display.
    check_dict : dict | None
        A dictionary that may contain items from data as keys.
    ui_buttons : bool
        If to display Buttons or not.
    ui_button_pos: str
        The side on which to show the buttons,
         'right', 'left', 'top' or 'bottom'.
    show_index: bool
        Set True if you want to display the list-index in front of each value.
    yes_bt: str
        Supply the name for a qt-standard-icon to mark
         the items existing in check_dict.
    no_bt: str
        Supply the name for a qt-standard-icon to mark
        the items not existing in check_dict.
    parent : QWidget | None
        Parent Widget (QWidget or inherited) or None if there is no parent.
    title : str | None
        An optional title.

    Notes
    -----
    If you change the contents of data outside of this class,
     call content_changed to update this widget.
    If you change the reference to data, call replace_data.
    If you change the reference to check_dict, call replace_check_dict.

    Names for QT standard-icons:
    https://doc.qt.io/qt-5/qstyle.html#StandardPixmap-enum
    """

    def __init__(
        self,
        data=None,
        check_dict=None,
        ui_buttons=True,
        ui_button_pos="right",
        extended_selection=False,
        show_index=False,
        yes_bt=None,
        no_bt=None,
        parent=None,
        title=None,
    ):
        model = CheckDictEditModel(
            data, check_dict, show_index=show_index, yes_bt=yes_bt, no_bt=no_bt
        )
        super().__init__(
            data=data,
            ui_buttons=ui_buttons,
            ui_button_pos=ui_button_pos,
            extended_selection=extended_selection,
            show_index=show_index,
            parent=parent,
            title=title,
            model=model,
        )

    def replace_check_dict(self, new_check_dict=None):
        """Replaces model.check_dict with new check_dict."""
        if new_check_dict:
            self.model._check_dict = new_check_dict
        self.content_changed()


class ProgressDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        """Paint an item with a progress background while preserving native
        checkbox + text rendering.

        Notes
        -----
        On some styles/backends (notably on Windows), the incoming `option`
        isn't guaranteed to be fully initialized for checkable items, and
        mutating it can result in an empty text rect. We therefore copy and
        initialize a fresh option, paint our background, then delegate the
        actual item drawing to Qt.
        """
        progress = index.data(CheckListProgressModel.ProgressRole) or 0
        try:
            progress = int(progress)
        except (TypeError, ValueError):
            progress = 0
        progress = max(0, min(100, progress))

        # Copy + init style option so checkbox/text geometry is correct.
        self.initStyleOption(option, index)

        # Draw progress background first on copied rect
        bar_rect = option.rect.adjusted(0, 0, 0, 0)
        bar_rect.setWidth(int(bar_rect.width() * (progress / 100)))

        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#4CAF50"))
        painter.drawRect(bar_rect)
        painter.restore()

        # Let the base delegate draw checkbox + icon + text.
        super().paint(painter, option, index)

    def sizeHint(self, option, index):
        opt = type(option)(option)
        self.initStyleOption(opt, index)
        return super().sizeHint(opt, index)


class CheckListProgress(CheckList):
    """A List-Widget to display items with a progress bar for each item. The
    progress in progress_dict is updated on content_changed or by calling
    update_progress.

    Parameters
    ----------
    data : list[str]
        A list with items to display.
    checked : list[str] | None
        Input a list, which will contain the checked items
        from data (and which intial items will be checked).
    progress_dict : dict | None
        A dictionary that may contain items from data as keys and
        their progress (0-100) as values.
    ui_buttons : bool
        If to display Buttons or not.
    one_check : bool
        If only one Item in the CheckList can be checked at the same time.
    show_index: bool
        Set True if you want to display the list-index in front of each value.
    parent : QWidget | None
        Parent Widget (QWidget or inherited) or None if there is no parent.
    title : str | None
        An optional title
    """

    def __init__(
        self,
        data,
        checked=None,
        progress_dict=None,
        ui_buttons=True,
        ui_button_pos="right",
        one_check=False,
        show_index=False,
        parent=None,
        title=None,
    ):
        self.progress_dict = progress_dict or {i: 0 for i in data}
        model = CheckListProgressModel(
            data, checked, progress_dict, one_check=one_check, show_index=show_index
        )
        super().__init__(
            ui_buttons=ui_buttons,
            ui_button_pos=ui_button_pos,
            parent=parent,
            title=title,
            model=model,
        )
        self.view.setItemDelegate(ProgressDelegate(self.view))

    def update_progress(self, item, progress):
        """Update the progress of a specific item.

        Parameters
        ----------
        item : str
            The item to update the progress for.
        progress : int
            The new progress value (0-100).
        """
        self.progress_dict[item] = progress
        self.content_changed()


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

        logging.debug(f"Current changed from {previous_list} to {current_list}")

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

        logging.debug(f"Selection changed to {selection_list}")

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
                for idx in zip(row, column):
                    indexes.append(idx)

        # Select complete rows
        if rows:
            # Convert names into indexes
            row_idxs = [list(self.model._data.index).index(row) for row in rows]
            n_cols = len(self.model._data.columns)
            for row in row_idxs:
                for idx in zip(itertools.repeat(row, n_cols), range(n_cols)):
                    indexes.append(idx)

        # Select complete columns
        if columns:
            # Convert names into indexes
            column_idxs = [list(self.model._data.columns).index(col) for col in columns]
            n_rows = len(self.model._data.index)
            for column in column_idxs:
                for idx in zip(range(n_rows), itertools.repeat(column, n_rows)):
                    indexes.append(idx)

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


class FilePandasTable(BasePandasTable):
    """A Widget to display the files in a table (stored in a pandas DataFrame)

    Parameters
    ----------
    data : pandas.DataFrame | None
        Input a pandas DataFrame with contents to display
    parent : QWidget | None
        Parent Widget (QWidget or inherited) or None if there is no parent
    title : str | None
        An optional title

    Notes
    -----
    If you change the Reference to data outside of this class,
    give the changed DataFrame to replace_data to update this widget
    """

    def __init__(self, data=None, parent=None, title=None):
        super().__init__(
            model=FileManagementModel(data),
            view=QTableView(),
            parent=parent,
            title=title,
            resize_rows=True,
            resize_columns=True,
        )


class TreeWidget(Base):
    """A widget to display hierarchical dictionary data with unlimited depth.

    This widget uses a tree view to display hierarchical data like nested dictionaries.
    It can handle dictionaries with unlimited nesting depth.

    Parameters
    ----------
    data : dict
        Dictionary with hierarchical data to be displayed
    headers : list[str] | None
        Headers for the columns. If None, default headers ["Key", "Value"] will be used.
    parent : QWidget | None
        Parent Widget (QWidget or inherited) or None if there is no parent.
    title : str | None
        An optional title.

    Notes
    -----
    If you change the contents of data outside of this class,
    call content_changed to update this widget.
    If you change the reference to data, call the appropriate replace_data.
    """

    def __init__(self, data=None, headers=None, parent=None, title=None):
        # Initialize the tree view
        view = QTreeView()
        view.setAlternatingRowColors(True)
        view.setSortingEnabled(True)
        view.setAnimated(True)
        view.setIndentation(20)
        view.setUniformRowHeights(True)

        # Create the model
        model = TreeModel(data, headers, parent)

        super().__init__(model=model, view=view, parent=parent, title=title)

        # Expand the first level by default
        self.view.expandToDepth(0)

    def content_changed(self):
        """Informs ModelView about external change made in data."""
        self.model.rebuild_tree()


class ShallowTreeWidget(Base):
    """A shallow grouped tree for ``dict[str, list]`` data with checkable keys.

    Top-level keys are checkable and mirrored in ``checked`` similarly to
    :class:`CheckList`.
    """

    checkedChanged = Signal(list)

    def __init__(
        self,
        data=None,
        checked=None,
        ui_buttons=True,
        ui_button_pos="right",
        headers=None,
        parent=None,
        title=None,
    ):
        self.ui_buttons = ui_buttons
        self.ui_button_pos = ui_button_pos

        view = QTreeView()
        view.setAlternatingRowColors(True)
        view.setAnimated(True)
        view.setIndentation(20)
        view.setUniformRowHeights(True)
        header = view.header()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)

        model = ShallowTreeModel(
            data=data, checked=checked, headers=headers, parent=parent
        )

        super().__init__(model=model, view=view, parent=parent, title=title)
        self.model.dataChanged.connect(self._checked_changed)

    def init_ui(self):
        if self.ui_button_pos in ["top", "bottom"]:
            layout = QVBoxLayout()
            bt_layout = QHBoxLayout()
        else:
            layout = QHBoxLayout()
            bt_layout = QVBoxLayout()

        if self.ui_buttons:
            add_group_bt = QPushButton("Add Group")
            add_group_bt.setSizePolicy(
                QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum
            )
            add_group_bt.clicked.connect(self.add_group)
            bt_layout.addWidget(add_group_bt)

            rm_group_bt = QPushButton("Remove Group")
            rm_group_bt.setSizePolicy(
                QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum
            )
            rm_group_bt.clicked.connect(self.remove_groups)
            bt_layout.addWidget(rm_group_bt)

            add_item_bt = QPushButton("Add Item")
            add_item_bt.setSizePolicy(
                QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum
            )
            add_item_bt.clicked.connect(self.add_item)
            bt_layout.addWidget(add_item_bt)

            rm_item_bt = QPushButton("Remove Item")
            rm_item_bt.setSizePolicy(
                QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum
            )
            rm_item_bt.clicked.connect(self.remove_items)
            bt_layout.addWidget(rm_item_bt)

            all_bt = QPushButton("All")
            all_bt.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
            all_bt.clicked.connect(self.select_all)
            bt_layout.addWidget(all_bt)

            clear_bt = QPushButton("Clear")
            clear_bt.setSizePolicy(
                QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum
            )
            clear_bt.clicked.connect(self.clear_all)
            bt_layout.addWidget(clear_bt)

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

    def _checked_changed(self):
        self.checkedChanged.emit(self.model._checked)
        logging.debug("Changed groups: %s", self.model._checked)

    def get_checked(self):
        return self.model._checked

    def _get_selected_group_keys(self):
        group_keys = set()
        for index in self.view.selectionModel().selectedIndexes():
            key = self.model.group_key_for_index(index)
            if key is not None:
                group_keys.add(key)

        if not group_keys:
            key = self.model.group_key_for_index(self.view.currentIndex())
            if key is not None:
                group_keys.add(key)

        return group_keys

    def _get_current_group_key(self):
        return self.model.group_key_for_index(self.view.currentIndex())

    def add_group(self):
        key = get_user_input("New group key:", "string")
        self.model.add_group(key)
        self.view.expandToDepth(0)

    def remove_groups(self):
        group_keys = self._get_selected_group_keys()
        removed = self.model.remove_groups(group_keys)
        if removed:
            self.checkedChanged.emit(self.model._checked)

    def add_item(self):
        group_key = self._get_current_group_key()
        if group_key is None:
            return

        item = get_user_input(f"New item for group '{group_key}':", "string")
        self.model.add_item(group_key, item)
        self.view.expandToDepth(0)

    def remove_items(self):
        grouped_rows = {}
        for index in self.view.selectionModel().selectedIndexes():
            if not self.model.is_item_index(index):
                continue
            group_key = self.model.group_key_for_index(index)
            grouped_rows.setdefault(group_key, set()).add(index.row())

        current = self.view.currentIndex()
        if not grouped_rows and self.model.is_item_index(current):
            group_key = self.model.group_key_for_index(current)
            grouped_rows[group_key] = {current.row()}

        for group_key, rows in grouped_rows.items():
            self.model.remove_items(group_key, rows)

    def replace_checked(self, new_checked):
        """Replaces ``model._checked`` with a new checked list."""
        self.model._checked = new_checked
        self.content_changed()
        self.checkedChanged.emit(self.model._checked)

    def select_all(self):
        """Check all top-level keys while preserving checked list reference."""
        for key in self.model._data:
            if key not in self.model._checked:
                self.model._checked.append(key)
        self.content_changed()
        self.checkedChanged.emit(self.model._checked)

    def clear_all(self):
        """Uncheck all keys while preserving checked list reference."""
        self.model._checked.clear()
        self.content_changed()
        self.checkedChanged.emit(self.model._checked)

    def content_changed(self):
        """Informs ModelView about external change made in data."""
        self.model.rebuild_tree()


class ComboBox(QComboBox):
    def __init__(self, scrollable=False, **kwargs):
        self.scrollable = scrollable
        super().__init__(**kwargs)

    def wheelEvent(self, event):
        if self.scrollable:
            super().wheelEvent(event)


class SimpleDialog(QDialog):
    def __init__(
        self,
        widget,
        parent=None,
        modal=True,
        scroll=False,
        title=None,
        window_title=None,
        show_close_bt=True,
    ):
        parent = parent or _widgets["main_window"] or _widgets["viewer"]
        super().__init__(parent)

        # Make sure, the dialog is deleted when closed
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        layout = QVBoxLayout()

        if title:
            layout.addWidget(QLabel(title))

        if window_title:
            self.setWindowTitle(window_title)

        if scroll:
            scroll_area = QScrollArea()
            scroll_area.setWidget(widget)
            layout.addWidget(scroll_area)
        else:
            layout.addWidget(widget)

        if show_close_bt:
            close_bt = QPushButton("Close")
            close_bt.clicked.connect(self.close)
            layout.addWidget(close_bt)

        self.setLayout(layout)

        if modal:
            self.open()
        else:
            self.show()


class AssignWidget(QWidget):
    """"""

    def __init__(
        self,
        items,
        properties,
        assignments,
        properties_editable=False,
        parent=None,
        title=None,
        subtitles=None,
    ):
        super().__init__(parent)
        self.title = title
        self.subtitles = subtitles

        self.items = items
        self.props = properties
        self.assignments = assignments
        self.props_editable = properties_editable

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        list_layout = QHBoxLayout()
        if self.subtitles is not None and len(self.subtitles) == 2:
            subtitle1, subtitle2 = self.subtitles
        else:
            subtitle1, subtitle2 = None, None

        self.items_w = CheckDictList(
            self.items, self.assignments, extended_selection=True, title=subtitle1
        )
        self.items_w.selectionChanged.connect(self.items_selected)
        list_layout.addWidget(self.items_w)

        if self.props_editable:
            self.props_w = EditList(
                self.props, extended_selection=False, title=subtitle2
            )
        else:
            self.props_w = SimpleList(
                self.props, extended_selection=False, title=subtitle2
            )
        list_layout.addWidget(self.props_w)
        layout.addLayout(list_layout)

        bt_layout = QHBoxLayout()
        assign_bt = QPushButton("Assign")
        assign_bt.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        assign_bt.setFont(QFont(Settings().get("app_font"), 13))
        assign_bt.clicked.connect(self.assign)
        bt_layout.addWidget(assign_bt)

        show_assign_bt = QPushButton("Show Assignments")
        show_assign_bt.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        show_assign_bt.setFont(QFont(Settings().get("app_font"), 13))
        show_assign_bt.clicked.connect(self.show_assignments)
        bt_layout.addWidget(show_assign_bt)
        layout.addLayout(bt_layout)

        if self.title:
            super_layout = QVBoxLayout()
            title_label = QLabel(self.title)
            title_label.setFont(QFont(Settings().get("app_font"), 14))
            super_layout.addWidget(title_label, alignment=Qt.AlignmentFlag.AlignHCenter)
            super_layout.addLayout(layout)
            self.setLayout(super_layout)
        else:
            self.setLayout(layout)

    def items_selected(self, selected):
        # Get all unique values of selected items
        values = {self.assignments[key] for key in selected if key in self.assignments}
        self.props_w.select(values)

    def assign(self):
        sel_items = self.items_w.get_selected()
        sel_prop = self.props_w.get_current()

        for item in sel_items:
            self.assignments[item] = sel_prop

        # Inform Model in CheckDict about change
        self.items_w.content_changed()

    def show_assignments(self):
        SimpleDialog(EditDict(self.assignments), parent=self, modal=False)


class TimedMessageBox(QMessageBox):
    def __init__(
        self, timeout=10, step_length=1000, title=None, text=None, *args, **kwargs
    ):
        super().__init__(*args, **kwargs)

        if title is not None:
            self.setWindowTitle(title)
        if text is not None:
            self.setText(text)

        self._got_clicked = False
        self.buttonClicked.connect(lambda: setattr(self, "_got_clicked", True))

        self.timeout = timeout
        self._update_timeout_text()

        # Start timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.countdown)
        self.timer.start(step_length)

    def _update_timeout_text(self):
        text = self.text()
        match = re.match(r"(.*)\nTimeout: \d+", text)
        if match:
            text = match.group(1)
        self.setText(f"{text}\nTimeout: {self.timeout}")

    def countdown(self):
        self._update_timeout_text()
        self.timeout -= 1
        if self.timeout <= 0:
            self.timer.stop()
            if self.defaultButton() is not None:
                self.defaultButton().click()
            else:
                self.close()

    @staticmethod
    def _static_setup(icon, timeout, parent, title, text, buttons, defaultButton):
        cls = TimedMessageBox(
            timeout=timeout, title=title, text=text, icon=icon, parent=parent
        )

        cls._update_timeout_text()
        cls.setStandardButtons(buttons)
        cls.setDefaultButton(defaultButton)
        ans = cls.exec()

        # Make sure ans is the default button if timeout is reached
        if not cls._got_clicked:
            ans = cls.defaultButton()

        return ans

    @staticmethod
    def critical(
        timeout=10,
        parent=None,
        title=None,
        text=None,
        buttons=QMessageBox.StandardButton.Ok,
        defaultButton=QMessageBox.StandardButton.NoButton,
    ):
        return TimedMessageBox._static_setup(
            QMessageBox.Icon.Critical,
            timeout,
            parent,
            title,
            text,
            buttons,
            defaultButton,
        )

    @staticmethod
    def information(
        timeout=10,
        parent=None,
        title=None,
        text=None,
        buttons=QMessageBox.StandardButton.Ok,
        defaultButton=QMessageBox.StandardButton.NoButton,
    ):
        return TimedMessageBox._static_setup(
            QMessageBox.Icon.Information,
            timeout,
            parent,
            title,
            text,
            buttons,
            defaultButton,
        )

    @staticmethod
    def question(
        timeout=10,
        parent=None,
        title=None,
        text=None,
        buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        defaultButton=QMessageBox.StandardButton.No,
    ):
        return TimedMessageBox._static_setup(
            QMessageBox.Icon.Question,
            timeout,
            parent,
            title,
            text,
            buttons,
            defaultButton,
        )

    @staticmethod
    def warning(
        timeout=10,
        parent=None,
        title=None,
        text=None,
        buttons=QMessageBox.StandardButton.Ok,
        defaultButton=QMessageBox.StandardButton.NoButton,
    ):
        return TimedMessageBox._static_setup(
            QMessageBox.Icon.Warning,
            timeout,
            parent,
            title,
            text,
            buttons,
            defaultButton,
        )
