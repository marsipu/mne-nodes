"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

from ast import literal_eval

import pandas as pd
from qtpy.QtCore import QAbstractItemModel, QAbstractTableModel, QModelIndex, Qt

from mne_nodes.logger import logger


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
            logger.warning(
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
                if isinstance(value, (dict, list)):
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
        self.beginInsertRows(parent or QModelIndex(), row, row + count - 1)
        add_data = pd.DataFrame(
            columns=self._data.columns, index=[r for r in range(count)]
        )
        if row == 0:
            self._data = pd.concat([add_data, self._data])
        elif row == len(self._data.index):
            self._data = pd.concat([self._data, add_data])
        else:
            self._data = pd.concat(
                [self._data.iloc[:row], add_data, self._data.iloc[row:]]
            )
        self.endInsertRows()

        return True

    def insertColumns(self, column, count, parent=None, *args, **kwargs):
        self.beginInsertColumns(parent or QModelIndex(), column, column + count - 1)
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
        self.beginRemoveRows(parent or QModelIndex(), row, row + count - 1)
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
        self.beginRemoveColumns(parent or QModelIndex(), column, column + count - 1)
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
