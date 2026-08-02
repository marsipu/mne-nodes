"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

from ast import literal_eval

from qtpy.QtCore import QAbstractItemModel, QAbstractTableModel, Qt

from mne_nodes.logger import logger


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
            logger.warning(
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
        if (
            not self.only_edit
            or index.column() == 0
            and self.only_edit == "keys"
            or index.column() == 1
            and self.only_edit == "values"
        ):
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
