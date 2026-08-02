"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

from mne_nodes.logger import logger
from ast import literal_eval

import qtawesome as qta
from qtpy.QtCore import QAbstractItemModel, QAbstractListModel, Qt


class BaseListModel(QAbstractListModel):
    """A basic List-Model.

    Parameters
    ----------
    data : list | None
        input existing list here, otherwise defaults to empty list
    show_index : bool
        Set True if you want to display the list-index in front of each value
    """

    def __init__(self, data=None, show_index=False, **kwargs):
        super().__init__(**kwargs)
        self.show_index = show_index
        if data is None:
            self._data = []
        else:
            # Only lists are supported; warn on wrong types
            if not isinstance(data, list):
                logger.warning(
                    "BaseListModel expects a list for 'data', got %s. Initializing empty list.",
                    type(data).__name__,
                )
                self._data = []
            else:
                self._data = data

    def getData(self, index):
        if not index or not index.isValid():
            logger.debug("Invalid model index")
            return None
        if len(self._data) == 0:
            logger.debug("List is empty")
            return None
        row = index.row()
        if row < 0 or row >= len(self._data):
            logger.debug("Row %s out of range (size=%s)", row, len(self._data))
            return None
        return self._data[row]

    def data(self, index, role=None):
        val = self.getData(index)
        if role == Qt.ItemDataRole.DisplayRole:
            if self.show_index:
                return f"{index.row()}: {val}" if val is not None else ""
            else:
                return "" if val is None else str(val)
        elif role == Qt.ItemDataRole.EditRole:
            return "" if val is None else str(val)

    def rowCount(self, *args, **kwargs):
        return len(self._data)

    def insertRows(self, row, count, parent=None, *args, **kwargs):
        self.beginInsertRows(parent, row, row + count - 1)
        n = 0
        for pos in range(row, row + count):
            item_name = f"__new{n}__"
            while item_name in self._data:
                n += 1
                item_name = f"__new{n}__"
            self._data.insert(pos, item_name)
        self.endInsertRows()
        return True

    def removeRows(self, row, count, parent=None, *args, **kwargs):
        self.beginRemoveRows(parent, row, row + count - 1)
        for item in [
            self._data[i] for i in range(row, row + count) if 0 <= i < len(self._data)
        ]:
            self._data.remove(item)
        self.endRemoveRows()
        return True

    def flags(self, index):
        default_flags = QAbstractListModel.flags(self, index)
        return default_flags


class EditListModel(BaseListModel):
    """An editable List-Model.

    Parameters
    ----------
    data : list
        input existing list here, otherwise defaults to empty list
    show_index: bool
        Set True if you want to display the list-index in front of each value
    """

    def __init__(self, data, show_index=False, **kwargs):
        super().__init__(data, show_index, **kwargs)

    def flags(self, index):
        default_flags = BaseListModel.flags(self, index)
        if index.isValid():
            return default_flags | Qt.ItemFlag.ItemIsEditable
        else:
            return default_flags

    def setData(self, index, value, role=None):
        if role == Qt.ItemDataRole.EditRole and index and index.isValid():
            try:
                self._data[index.row()] = literal_eval(value)
            except (ValueError, SyntaxError):
                self._data[index.row()] = value
            self.dataChanged.emit(index, index)
            return True
        return False


class CheckListModel(BaseListModel):
    """A Model for a Check-List.

    Parameters
    ----------
    data : list | None
        list with content to be displayed, defaults to empty list
    checked : list | None
        list which stores the checked items from data
    show_index: bool
        Set True if you want to display the list-index in front of each value
    """

    def __init__(self, data, checked, one_check=False, show_index=False, **kwargs):
        super().__init__(data, show_index, **kwargs)
        self.one_check = one_check

        # Enforce list types for data and checked
        if data is None:
            self._data = []
        elif not isinstance(data, list):
            logger.warning(
                "CheckListModel expects a list for 'data', got %s. Initializing empty list.",
                type(data).__name__,
            )
            self._data = []
        else:
            self._data = data

        if checked is None:
            self._checked = []
        elif not isinstance(checked, list):
            logger.warning(
                "CheckListModel expects a list for 'checked', got %s. Initializing empty list.",
                type(checked).__name__,
            )
            self._checked = []
        else:
            self._checked = checked

    def data(self, index, role=None):
        val = self.getData(index)
        if role == Qt.ItemDataRole.DisplayRole:
            if self.show_index:
                return f"{index.row()}: {val}" if val is not None else ""
            else:
                return "" if val is None else str(val)

        if role == Qt.ItemDataRole.CheckStateRole:
            if val is None:
                return None
            return (
                Qt.CheckState.Checked
                if val in self._checked
                else Qt.CheckState.Unchecked
            )

    def setData(self, index, value, role=None):
        if role == Qt.ItemDataRole.CheckStateRole and index and index.isValid():
            val = self.getData(index)
            if val is None:
                return False
            # In PyQt5 value is an integer, in PySide6 it is a Qt.CheckState
            if value in [Qt.CheckState.Checked, 2]:
                if self.one_check:
                    self._checked.clear()
                if val not in self._checked:
                    self._checked.append(val)
            else:
                if val in self._checked:
                    self._checked.remove(val)
            self.dataChanged.emit(index, index)
            return True
        return False

    def flags(self, index):
        return QAbstractItemModel.flags(self, index) | Qt.ItemFlag.ItemIsUserCheckable


class CheckDictModel(BaseListModel):
    """A Model for a list, which marks items which are present in a dictionary.

    Parameters
    ----------
    data : []
        list with content to be displayed, defaults to empty list
    check_dict : {}
        dictionary which may contain items from data as keys
    show_index: bool
        Set True if you want to display the list-index in front of each value
    yes_bt: str
        Supply the name for a qt-standard-icon to mark the items
        existing in check_dict
    no_bt: str
        Supply the name for a qt-standard-icon to mark the items
        not existing in check_dict

    Notes
    -----
    Names for QT awesome icons:
    https://github.com/spyder-ide/qtawesome
    """

    def __init__(
        self, data, check_dict, show_index=False, yes_bt=None, no_bt=None, **kwargs
    ):
        super().__init__(data, show_index, **kwargs)
        # Enforce list for data and dict for check_dict
        if data is None:
            self._data = []
        elif not isinstance(data, list):
            logger.warning(
                "CheckDictModel expects a list for 'data', got %s. Initializing empty list.",
                type(data).__name__,
            )
            self._data = []
        else:
            self._data = data

        if check_dict is None:
            self._check_dict = {}
        elif not isinstance(check_dict, dict):
            logger.warning(
                "CheckDictModel expects a dict for 'check_dict', got %s. Initializing empty dict.",
                type(check_dict).__name__,
            )
            self._check_dict = {}
        else:
            self._check_dict = check_dict

        self.yes_bt = yes_bt or "fa5s.check"
        self.no_bt = no_bt or "fa5s.times"

    def data(self, index, role=None):
        val = self.getData(index)
        if role == Qt.ItemDataRole.DisplayRole:
            if self.show_index:
                return f"{index.row()}: {val}" if val is not None else ""
            else:
                return "" if val is None else str(val)
        elif role == Qt.ItemDataRole.EditRole:
            return "" if val is None else str(val)

        elif role == Qt.ItemDataRole.DecorationRole:
            if val is None:
                return None
            if val in self._check_dict:
                return qta.icon(self.yes_bt)
            else:
                return qta.icon(self.no_bt)


class CheckDictEditModel(CheckDictModel, EditListModel):
    """An editable List-Model.

    Parameters
    ----------
    data : []
        list with content to be displayed, defaults to empty list
    check_dict : {}
        dictionary which may contain items from data as keys
    show_index: bool
        Set True if you want to display the list-index in front of each value
    yes_bt: str
        Supply the name for a qt-awesome icon to mark the items
         existing in check_dict
    no_bt: str
        Supply the name for a qt-awesome icon to mark the items
        not existing in check_dict

    Notes
    -----
    Names for QT awesome icons:
    https://github.com/spyder-ide/qtawesome
    """

    def __init__(self, data, check_dict, show_index=False, yes_bt=None, no_bt=None):
        super().__init__(data, check_dict, show_index, yes_bt, no_bt)
        # EditListModel doesn't have to be initialized
        # because in __init__ of EditListModel
        # only BaseListModel is initialized which is already done
        # in __init__ of CheckDictModel


class CheckListProgressModel(CheckListModel):
    """A Model for a Check-List with progress information.

    Parameters
    ----------
    data : list | None
        list with content to be displayed, defaults to empty list
    checked : list | None
        list which stores the checked items from data
    progress_dict : dict | None
        dictionary which stores progress information for items in data
    one_check: bool
        If True, only one item can be checked at a time
    show_index: bool
        Set True if you want to display the list-index in front of each value
    """

    ProgressRole = Qt.ItemDataRole.UserRole + 1

    def __init__(
        self,
        data,
        checked,
        progress_dict=None,
        one_check=False,
        show_index=False,
        **kwargs,
    ):
        super().__init__(data, checked, one_check, show_index, **kwargs)
        self._progress_dict = progress_dict or {}

    def data(self, index, role=None):
        if role == self.ProgressRole:
            val = self.getData(index)
            if val is None:
                return 0
            return self._progress_dict.get(val, 0)
        else:
            return super().data(index, role)

    def roleNames(self):
        roles = super().roleNames()
        roles[self.ProgressRole] = b"progress"
        return roles
