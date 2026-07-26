"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

from qtpy.QtCore import QAbstractTableModel, QMimeData, Qt


class FunctionPickerModel(QAbstractTableModel):
    """Simple table model for draggable function entries in the node picker."""

    _headers = ["Name", "Module", "Description"]

    def __init__(self, function_meta, parent=None):
        super().__init__(parent)
        self._function_meta = function_meta or {}
        self._rows = list(self._function_meta.keys())

    def rowCount(self, parent=None):
        return len(self._rows)

    def columnCount(self, parent=None):
        return len(self._headers)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(self._headers):
                return self._headers[section]
            return None
        return str(section)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        func_name = self._rows[index.row()]
        meta = self._function_meta.get(func_name, {})

        if role == Qt.ItemDataRole.DisplayRole:
            if index.column() == 0:
                return func_name
            if index.column() == 1:
                return str(meta.get("module", ""))
            if index.column() == 2:
                return str(meta.get("description", ""))
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.ItemIsEnabled
        return (
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsDragEnabled
        )

    def mimeData(self, indexes):
        mime = QMimeData()
        if not indexes:
            return mime

        first = indexes[0]
        if first.isValid():
            mime.setText(self._rows[first.row()])
        return mime

    def supportedDragActions(self):
        return Qt.DropAction.CopyAction

    def sort(self, column, order=Qt.SortOrder.AscendingOrder):
        reverse = order == Qt.SortOrder.DescendingOrder

        def sort_key(name):
            meta = self._function_meta.get(name, {})
            if column == 0:
                return name
            if column == 1:
                return str(meta.get("module", ""))
            return str(meta.get("description", ""))

        self.layoutAboutToBeChanged.emit()
        self._rows.sort(key=sort_key, reverse=reverse)
        self.layoutChanged.emit()
