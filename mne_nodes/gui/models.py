"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import logging
from ast import literal_eval
from datetime import datetime

import pandas as pd
from qtpy.QtCore import (
    QAbstractItemModel,
    QAbstractListModel,
    QAbstractTableModel,
    QModelIndex,
    Qt,
    QMimeData,
)
from qtpy.QtGui import QBrush, QFont

from mne_nodes.gui.gui_utils import get_std_icon


# ToDo: Merge models and base widgets


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
                logging.warning(
                    "BaseListModel expects a list for 'data', got %s. Initializing empty list.",
                    type(data).__name__,
                )
                self._data = []
            else:
                self._data = data

    def getData(self, index):
        if not index or not index.isValid():
            logging.debug("Invalid model index")
            return None
        if len(self._data) == 0:
            logging.debug("List is empty")
            return None
        row = index.row()
        if row < 0 or row >= len(self._data):
            logging.debug("Row %s out of range (size=%s)", row, len(self._data))
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
            logging.warning(
                "CheckListModel expects a list for 'data', got %s. Initializing empty list.",
                type(data).__name__,
            )
            self._data = []
        else:
            self._data = data

        if checked is None:
            self._checked = []
        elif not isinstance(checked, list):
            logging.warning(
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
    Names for QT standard-icons:
    https://doc.qt.io/qt-5/qstyle.html#StandardPixmap-enum
    """

    def __init__(
        self, data, check_dict, show_index=False, yes_bt=None, no_bt=None, **kwargs
    ):
        super().__init__(data, show_index, **kwargs)
        # Enforce list for data and dict for check_dict
        if data is None:
            self._data = []
        elif not isinstance(data, list):
            logging.warning(
                "CheckDictModel expects a list for 'data', got %s. Initializing empty list.",
                type(data).__name__,
            )
            self._data = []
        else:
            self._data = data

        if check_dict is None:
            self._check_dict = {}
        elif not isinstance(check_dict, dict):
            logging.warning(
                "CheckDictModel expects a dict for 'check_dict', got %s. Initializing empty dict.",
                type(check_dict).__name__,
            )
            self._check_dict = {}
        else:
            self._check_dict = check_dict

        self.yes_bt = yes_bt or "SP_DialogApplyButton"
        self.no_bt = no_bt or "SP_DialogCancelButton"

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
                return get_std_icon(self.yes_bt)
            else:
                return get_std_icon(self.no_bt)


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
        Supply the name for a qt-standard-icon to mark the items
         existing in check_dict
    no_bt: str
        Supply the name for a qt-standard-icon to mark the items
        not existing in check_dict

    Notes
    -----
    Names for QT standard-icons:
    https://doc.qt.io/qt-5/qstyle.html#StandardPixmap-enum
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


class BaseDictModel(QAbstractTableModel):
    """Basic Model for Dictonaries.

    Parameters
    ----------
    data : dict | OrderedDict | None
        Dictionary with keys and values to be displayed,
         default to empty Dictionary

    Notes
    -----
    Python 3.7 is required to ensure order in dictionary
     when inserting a normal dict (or use OrderedDict)
    """

    def __init__(self, data=None, **kwargs):
        super().__init__(**kwargs)
        if data is None:
            self._data = {}
        elif not isinstance(data, dict):
            logging.warning(
                "BaseDictModel expects a dict for 'data', got %s. Initializing empty dict.",
                type(data).__name__,
            )
            self._data = {}
        else:
            self._data = data

    def getData(self, index):
        try:
            if index.column() == 0:
                return list(self._data.keys())[index.row()]
            elif index.column() == 1:
                return list(self._data.values())[index.row()]
        # Happens, when a duplicate key is entered
        except IndexError:
            self.layoutChanged.emit()
            return ""

    def data(self, index, role=None):
        if role == Qt.ItemDataRole.DisplayRole or role == Qt.ItemDataRole.EditRole:
            return str(self.getData(index))

    def headerData(self, idx, orientation, role=None):
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                if idx == 0:
                    return "Key"
                elif idx == 1:
                    return "Value"
            elif orientation == Qt.Orientation.Vertical:
                return str(idx)

    def rowCount(self, parent=None, *args, **kwargs):
        return len(self._data)

    def columnCount(self, parent=None, *args, **kwargs):
        return 2


# ToDo: Somehow inputs are automatically sorted (annoyig, disable-toggle)
class EditDictModel(BaseDictModel):
    """An editable model for Dictionaries.

    Parameters
    ----------
    data : dict | OrderedDict | None
        Dictionary with keys and values to be displayed,
         default to empty Dictionary

    only_edit : 'keys' | 'values' | None
        Makes only keys or only values editable. Both are editable if None.

    Notes
    -----
    Python 3.7 is required to ensure order in dictionary
     when inserting a normal dict (or use OrderedDict)
    """

    def __init__(self, data=None, only_edit=None, **kwargs):
        super().__init__(data, **kwargs)
        self.only_edit = only_edit

    def setData(self, index, value, role=None):
        if role == Qt.ItemDataRole.EditRole:
            try:
                value = literal_eval(value)
            except (SyntaxError, ValueError):
                pass
            if index.column() == 0:
                self._data[value] = self._data.pop(list(self._data.keys())[index.row()])
            elif index.column() == 1:
                self._data[list(self._data.keys())[index.row()]] = value
            else:
                return False

            self.dataChanged.emit(index, index, [role])
            return True

        return False

    def flags(self, index):
        if not self.only_edit:
            return QAbstractItemModel.flags(self, index) | Qt.ItemFlag.ItemIsEditable
        elif index.column() == 0 and self.only_edit == "keys":
            return QAbstractItemModel.flags(self, index) | Qt.ItemFlag.ItemIsEditable
        elif index.column() == 1 and self.only_edit == "values":
            return QAbstractItemModel.flags(self, index) | Qt.ItemFlag.ItemIsEditable
        else:
            return QAbstractItemModel.flags(self, index)

    def insertRows(self, row, count, parent=None, *args, **kwargs):
        self.beginInsertRows(parent, row, row + count - 1)
        for n in range(count):
            key_name = f"__new{n}__"
            while key_name in self._data.keys():
                n += 1
                key_name = f"__new{n}__"
            self._data[key_name] = ""
        self.endInsertRows()

        return True

    def removeRows(self, row, count, parent=None, *args, **kwargs):
        self.beginRemoveRows(parent, row, row + count - 1)
        for n in range(count):
            self._data.pop(list(self._data.keys())[row + n])
        self.endRemoveRows()

        return True


class BasePandasModel(QAbstractTableModel):
    """Basic Model for pandas DataFrame.

    Parameters
    ----------
    data : pandas.DataFrame | None
        pandas DataFrame with contents to be displayed,
        defaults to empty DataFrame
    """

    def __init__(self, data=None, **kwargs):
        super().__init__(**kwargs)
        if data is None:
            self._data = pd.DataFrame([])
        elif not isinstance(data, pd.DataFrame):
            logging.warning(
                "BasePandasModel expects a pandas DataFrame for 'data', got %s. Initializing empty DataFrame.",
                type(data).__name__,
            )
            self._data = pd.DataFrame([])
        else:
            self._data = data

    def getData(self, index):
        return self._data.iloc[index.row(), index.column()]

    def data(self, index, role=None):
        if role == Qt.ItemDataRole.DisplayRole or role == Qt.ItemDataRole.EditRole:
            return str(self.getData(index))

    def headerData(self, idx, orientation, role=None):
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                return str(self._data.columns[idx])
            elif orientation == Qt.Orientation.Vertical:
                return str(self._data.index[idx])

    def rowCount(self, parent=None, *args, **kwargs):
        return len(self._data.index)

    def columnCount(self, parent=None, *args, **kwargs):
        return len(self._data.columns)


class EditPandasModel(BasePandasModel):
    """Editable TableModel for Pandas DataFrames.

    Parameters
    ----------
    data : pandas.DataFrame | None
        pandas DataFrame with contents to be displayed,
         defaults to empty DataFrame

    Notes
    -----
    The reference of the original input-DataFrame is lost
     when edited by this Model,
    you need to retrieve it directly from the model after editing
    """

    def __init__(self, data=None, **kwargs):
        super().__init__(data, **kwargs)

    def setData(self, index, value, role=None):
        if role == Qt.ItemDataRole.EditRole:
            try:
                value = literal_eval(value)
                # List or Dictionary not allowed here as PandasDataFrame-Item
                if isinstance(value, dict) or isinstance(value, list):
                    value = str(value)
            except (SyntaxError, ValueError):
                pass
            self._data.iloc[index.row(), index.column()] = value
            self.dataChanged.emit(index, index, [role])
            return True

        return False

    def setHeaderData(self, index, orientation, value, role=Qt.ItemDataRole.EditRole):
        if role == Qt.ItemDataRole.EditRole:
            if orientation == Qt.Orientation.Vertical:
                # DataFrame.rename does rename all duplicate indices
                # if existent, that's why the index is reassigned directly
                new_index = list(self._data.index)
                new_index[index] = value
                self._data.index = new_index
                self.headerDataChanged.emit(Qt.Orientation.Vertical, index, index)
                return True

            elif orientation == Qt.Orientation.Horizontal:
                # DataFrame.rename does rename all duplicate columns
                # if existent, that's why the columns are reassigned directly
                new_columns = list(self._data.columns)
                new_columns[index] = value
                self._data.columns = new_columns
                self.headerDataChanged.emit(Qt.Orientation.Horizontal, index, index)
                return True

        return False

    def flags(self, index):
        return QAbstractItemModel.flags(self, index) | Qt.ItemFlag.ItemIsEditable

    def insertRows(self, row, count, parent=None, *args, **kwargs):
        self.beginInsertRows(parent, row, row + count - 1)
        add_data = pd.DataFrame(
            columns=self._data.columns, index=[r for r in range(count)]
        )
        if row == 0:
            self._data = pd.concat([add_data, self._data])
        elif row == len(self._data.index):
            self._data = self._data.append(add_data)
        else:
            self._data = pd.concat(
                [self._data.iloc[:row], add_data, self._data.iloc[row:]]
            )
        self.endInsertRows()

        return True

    def insertColumns(self, column, count, parent=None, *args, **kwargs):
        self.beginInsertColumns(parent, column, column + count - 1)
        add_data = pd.DataFrame(
            index=self._data.index, columns=[c for c in range(count)]
        )
        if column == 0:
            self._data = pd.concat([add_data, self._data], axis=1)
        elif column == len(self._data.columns):
            self._data = pd.concat([self._data, add_data], axis=1)
        else:
            self._data = pd.concat(
                [self._data.iloc[:, :column], add_data, self._data.iloc[:, column:]],
                axis=1,
            )
        self.endInsertColumns()

        return True

    def removeRows(self, row, count, parent=None, *args, **kwargs):
        self.beginRemoveRows(parent, row, row + count - 1)
        # Can't use DataFrame.drop() here,
        # because there could be rows with similar index-labels
        if row == 0:
            self._data = self._data.iloc[row + count :]
        elif row + count >= len(self._data.index):
            self._data = self._data.iloc[:row]
        else:
            self._data = pd.concat(
                [self._data.iloc[:row], self._data.iloc[row + count :]]
            )
        self.endRemoveRows()

        return True

    def removeColumns(self, column, count, parent=None, *args, **kwargs):
        self.beginRemoveColumns(parent, column, column + count - 1)
        # Can't use DataFrame.drop() here,
        # because there could be columns with similar column-labels
        if column == 0:
            self._data = self._data.iloc[:, column + count :]
        elif column + count >= len(self._data.columns):
            self._data = self._data.iloc[:, :column]
        else:
            self._data = pd.concat(
                [self._data.iloc[:, :column], self._data.iloc[:, column + count :]],
                axis=1,
            )
        self.endRemoveColumns()

        return True


class TreeItem:
    """TreeItem for TreeModel.

    Parameters
    ----------
    data : list
        List with data for the item, first element is the key,
        the rest are empty strings for additional columns
    parent : TreeItem or None
        Parent item, defaults to None for root item
    """

    def __init__(self, data, parent=None):
        self._data = data
        self._parent = parent
        self._children = []

    def child(self, number):
        if 0 <= number < len(self._children):
            return self._children[number]

    def childCount(self):
        return len(self._children)

    def row(self):
        if self._parent:
            return self._parent._children.index(self)
        return 0

    def columnCount(self):
        return len(self._data)

    def data(self, column):
        if 0 <= column < len(self._data):
            return self._data[column]

    def setData(self, column, value):
        if 0 <= column < len(self._data):
            self._data[column] = value
            return True
        return False

    def insertChild(self, position):
        if 0 <= position < len(self._children):
            self._children.insert(
                position, TreeItem([f"__new__{len(self._children)}"], self)
            )
            return True
        return False

    def removeChild(self, position):
        if 0 <= position < len(self._children):
            self._children.remove(self._children[position])
            return True
        return False

    def insertColumn(self, position):
        if 0 <= position < len(self._data):
            self._data.insert(position, f"__new__{len(self._data)}")
            for child in self._children:
                child.insertColumns(position)
            return True
        return False

    def removeColumn(self, position):
        if 0 <= position < len(self._data):
            self._data.remove(self._data[position])
            for child in self._children:
                child.removeColumns(position)
            return True
        return False


class TreeModel(QAbstractItemModel):
    """A model for displaying hierarchical dictionary data with unlimited
    depth.

    Parameters
    ----------
    data : dict
        Dictionary with hierarchical data to be displayed
    headers : list[str] | None
        Headers for the columns. If None, default headers will be used.
    parent : QWidget | None
        Parent widget
    """

    def __init__(self, data=None, headers=None, parent=None):
        super().__init__(parent)
        if data is None:
            self._data = {}
        elif not isinstance(data, dict):
            logging.warning(
                "TreeModel expects a dict for 'data', got %s. Initializing empty dict.",
                type(data).__name__,
            )
            self._data = {}
        else:
            self._data = data

        # Default headers for key-value pairs
        if headers is None:
            self._headers = ["Key", "Value"]
        else:
            self._headers = headers

        self._parent = parent

        # Create the root item
        self.root_item = self._build_tree(self._data)

    def _build_tree(self, data):
        """Build the tree structure from the hierarchical dictionary data."""
        root = TreeItem(self._headers)

        def add_items(parent_item, dict_data):
            for key, value in dict_data.items():
                # For each key-value pair, create a tree item
                if isinstance(value, dict):
                    # If value is a dictionary, create a branch
                    item_data = [key, f"{len(value)} items"]
                    child = TreeItem(item_data, parent_item)
                    parent_item._children.append(child)
                    # Recursively add children
                    add_items(child, value)
                else:
                    # If value is not a dictionary, create a leaf
                    item_data = [key, str(value)]
                    child = TreeItem(item_data, parent_item)
                    parent_item._children.append(child)

        # Start building the tree
        add_items(root, data)
        return root

    def getData(self, index):
        """Get data at the specified index.

        This method is required by the Base widget class.
        """
        if not index.isValid():
            return None

        item = index.internalPointer()
        return item.data(index.column())

    def data(self, index, role=None):
        if not index.isValid():
            return None

        if role == Qt.ItemDataRole.DisplayRole:
            item = index.internalPointer()
            return item.data(index.column())

        return None

    def headerData(self, section, orientation, role=None):
        if (
            orientation == Qt.Orientation.Horizontal
            and role == Qt.ItemDataRole.DisplayRole
        ):
            if 0 <= section < len(self._headers):
                return self._headers[section]
        return None

    def index(self, row, column, parent=None, *args, **kwargs):
        if not self.hasIndex(row, column, parent):
            return QModelIndex()

        if not parent.isValid():
            parent_item = self.root_item
        else:
            parent_item = parent.internalPointer()

        child_item = parent_item.child(row)
        if child_item:
            return self.createIndex(row, column, child_item)
        return QModelIndex()

    def parent(self, index=None):
        if not index.isValid():
            return QModelIndex()

        child_item = index.internalPointer()
        parent_item = child_item._parent

        if parent_item == self.root_item:
            return QModelIndex()

        return self.createIndex(parent_item.row(), 0, parent_item)

    def rowCount(self, parent=None, *args, **kwargs):
        if parent.column() > 0:
            return 0

        if not parent.isValid():
            parent_item = self.root_item
        else:
            parent_item = parent.internalPointer()

        return parent_item.childCount()

    def columnCount(self, parent=None, *args, **kwargs):
        return len(self._headers)

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags

        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable


class AddFilesModel(BasePandasModel):
    def __init__(self, data, **kwargs):
        super().__init__(data, **kwargs)

    def data(self, index, role=None):
        column = self._data.columns[index.column()]

        if role == Qt.ItemDataRole.DisplayRole:
            if column != "Empty-Room?":
                return str(self.getData(index))
            else:
                return ""

        elif role == Qt.ItemDataRole.CheckStateRole:
            if column == "Empty-Room?":
                if self.getData(index):
                    return Qt.CheckState.Checked
                else:
                    return Qt.CheckState.Unchecked

    def setData(self, index, value, role=None):
        if (
            role == Qt.ItemDataRole.CheckStateRole
            and self._data.columns[index.column()] == "Empty-Room?"
        ):
            if value == Qt.CheckState.Checked:
                self._data.iloc[index.row(), index.column()] = 1
            else:
                self._data.iloc[index.row(), index.column()] = 0
            self.dataChanged.emit(index, index, [role])
            return True

        return False

    def flags(self, index):
        if self._data.columns[index.column()] == "Empty-Room?":
            return (
                QAbstractItemModel.flags(self, index) | Qt.ItemFlag.ItemIsUserCheckable
            )

        return QAbstractItemModel.flags(self, index)


class FileManagementModel(BasePandasModel):
    """A model for the Pandas-DataFrames containing information about the
    existing files."""

    def __init__(self, data, **kwargs):
        super().__init__(data, **kwargs)

    def data(self, index, role=None):
        value = self.getData(index)
        if role == Qt.ItemDataRole.DisplayRole:
            if pd.isna(value) or value in [
                "existst",
                "possible_conflict",
                "critical_conflict",
            ]:
                pass
            elif isinstance(value, datetime):
                return value.strftime("%d.%m.%y %H:%M")
            elif isinstance(value, float):
                if value == 0:
                    pass
                elif value / 1024 < 1000:
                    return f"{int(value / 1024)} KB"
                else:
                    return f"{int(value / (1024**2))} MB"

        if role == Qt.ItemDataRole.DecorationRole:
            if pd.isna(value) or value == 0:
                return get_std_icon("SP_DialogCancelButton")
            elif value == "exists":
                return get_std_icon("SP_DialogApplyButton")
            elif value == "possible_conflict":
                return get_std_icon("SP_MessageBoxQuestion")
            elif value == "critical_conflict":
                return get_std_icon("SP_MessageBoxWarning")

        elif role == Qt.ItemDataRole.BackgroundRole:
            if pd.isna(value) or value == 0:
                return QBrush(Qt.GlobalColor.darkRed)
            elif value == "exists":
                return QBrush(Qt.GlobalColor.green)
            elif value == "possible_conflict":
                return QBrush(Qt.GlobalColor.lightGray)
            elif value == "critical_conflict":
                return QBrush(Qt.GlobalColor.darkYellow)


# ------------------------ NodePicker Models -------------------------------
class PickerModel(BasePandasModel):
    """Base model for NodePicker with common functionality.

    Parameters
    ----------
    data : pandas.DataFrame | None
        DataFrame with contents to be displayed, defaults to empty DataFrame.
    """

    def __init__(self, data=None, **kwargs):
        if data is None:
            data = pd.DataFrame([])
        super().__init__(data, **kwargs)

    def flags(self, index):
        return QAbstractItemModel.flags(self, index) | Qt.ItemFlag.ItemIsDragEnabled

    def mimeTypes(self):
        return ["text/plain"]

    def supportedDragActions(self):
        return Qt.DropAction.CopyAction

    def sort(self, column: int, order: Qt.SortOrder):
        self.layoutAboutToBeChanged.emit()
        self._data.sort_values(
            self._data.columns[column],
            axis=0,
            inplace=True,
            ascending=order == Qt.SortOrder.AscendingOrder,
        )
        self.layoutChanged.emit()


class FunctionPickerModel(PickerModel):
    """Draggable model for functions list used in NodePicker.

    Parameters
    ----------
    function_meta : dict
        Dictionary with function metadata, where keys are function names
    """

    def __init__(self, function_meta: dict, **kwargs):
        # Build dataframe with only inputs/outputs columns
        rows = []
        self.alias_dict = {
            meta.get("alias", k) or k: k for k, meta in function_meta.items()
        }
        for fname, meta in (function_meta or {}).items():
            rows.append(
                {
                    "name": meta.get("alias", None) or fname,
                    "inputs": ", ".join(meta.get("inputs", [])),
                    "outputs": ", ".join(meta.get("outputs", [])),
                }
            )
        df = pd.DataFrame(rows)
        super().__init__(df, **kwargs)
        self._metas = function_meta or {}

    def mimeData(self, indexes):
        mime = super().mimeData(indexes)
        # Use first index row
        if len(indexes) == 0:
            return mime
        row = indexes[0].row()
        fname = self.alias_dict[self._data.iloc[row, 0]]

        md = QMimeData()
        md.setText(f"mne-nodes/function:{fname}")
        return md

    def data(self, index, role=None):
        if role == Qt.ItemDataRole.ToolTipRole:
            fname = self._data.index[index.row()]
            meta = self._metas.get(fname, {})
            alias = meta.get("alias")
            group = meta.get("group")
            module = meta.get("module")
            nparams = len(meta.get("parameters", []))
            plot = meta.get("plot", False)
            tsafe = meta.get("thread-safe", False)
            return (
                f"{fname} ({alias})\nGroup: {group}\nModule: {module}\n"
                f"Inputs: {', '.join(meta.get('inputs', []))}\n"
                f"Outputs: {', '.join(meta.get('outputs', []))}\n"
                f"Parameters: {nparams}\nPlot: {plot}  Thread-safe: {tsafe}"
            )
        return super().data(index, role)


class CustomFunctionModel(QAbstractListModel):
    """A Model for the Pandas-DataFrames containing information about new
    custom functions/their paramers to display only their name and if they are
    ready.

    Parameters
    ----------
    data : DataFrame
    add_pd_funcs or add_pd_params
    """

    def __init__(self, data, **kwargs):
        super().__init__(**kwargs)
        if not isinstance(data, pd.DataFrame):
            logging.warning(
                "CustomFunctionModel expects a pandas DataFrame for 'data', got %s. Initializing empty DataFrame.",
                type(data).__name__,
            )
            self._data = pd.DataFrame([])
        else:
            self._data = data
        if not self._data.empty and "ready" not in self._data.columns:
            logging.warning(
                "CustomFunctionModel expects a 'ready' column in DataFrame to decorate items. Column missing."
            )

    def getData(self, index):
        return self._data.index[index.row()]

    def updateData(self, new_data):
        self._data = new_data
        self.layoutChanged.emit()

    def data(self, index, role=None):
        if role == Qt.ItemDataRole.DisplayRole:
            return str(self.getData(index))

        elif role == Qt.ItemDataRole.DecorationRole:
            if self._data.loc[self.getData(index), "ready"]:
                return get_std_icon("SP_DialogApplyButton")
            else:
                return get_std_icon("SP_DialogCancelButton")

    def rowCount(self, parent=None, *args, **kwargs):
        return len(self._data.index)


class RunModel(QAbstractListModel):
    """A model for the items/functions of a Pipeline-Run."""

    def __init__(self, data, mode, **kwargs):
        super().__init__(**kwargs)
        if not isinstance(data, dict):
            logging.warning(
                "RunModel expects a dict for 'data', got %s. Initializing empty dict.",
                type(data).__name__,
            )
            self._data = {}
        else:
            self._data = data
        self.mode = mode

    def getKey(self, index):
        return list(self._data.keys())[index.row()]

    def getValue(self, index):
        if self.mode == "object":
            return self._data[self.getKey(index)]["status"]
        else:
            return self._data[self.getKey(index)]

    def getType(self, index):
        return self._data[self.getKey(index)]["type"]

    def data(self, index, role=None):
        if role == Qt.ItemDataRole.DisplayRole:
            if self.mode == "object":
                return f"{self.getType(index)}: {self.getKey(index)}"
            return self.getKey(index)

        # Object/Function-States:
        # 0 = Finished
        # 1 = Pending
        # 2 = Currently Runnning
        # Return Foreground depending on state of object/function
        elif role == Qt.ItemDataRole.ForegroundRole:
            if self.getValue(index) == 0:
                return QBrush(Qt.GlobalColor.darkGray)
            elif self.getValue(index) == 2:
                return QBrush(Qt.GlobalColor.green)

        # Return Background depending on state of object/function
        elif role == Qt.ItemDataRole.BackgroundRole:
            if self.getValue(index) == 2:
                return QBrush(Qt.GlobalColor.darkGreen)

        # Mark objects/functions if they are already done,
        # mark objects according to their type (color-code)
        elif role == Qt.ItemDataRole.DecorationRole:
            if self.getValue(index) == 0:
                return get_std_icon("SP_DialogApplyButton")
            elif self.getValue(index) == 2:
                return get_std_icon("SP_ArrowRight")

        elif role == Qt.ItemDataRole.FontRole:
            if self.getValue(index) == 2:
                bold_font = QFont()
                bold_font.setBold(True)
                return bold_font

    def rowCount(self, parent=None, *args, **kwargs):
        return len(self._data)
