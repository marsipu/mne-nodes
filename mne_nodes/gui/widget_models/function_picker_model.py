"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

from typing import ClassVar

from qtpy.QtCore import QAbstractItemModel, QMimeData, QModelIndex, Qt


class _FunctionItem:
    def __init__(self, name, kind, metadata=None, parent=None):
        self.name = name
        self.kind = kind
        self.metadata = metadata or {}
        self.parent = parent
        self.children = []


class FunctionPickerModel(QAbstractItemModel):
    """Hierarchical model for draggable, categorized function entries."""

    _headers: ClassVar[list[str]] = ["Name", "Module", "Description"]

    def __init__(self, function_meta, parent=None):
        super().__init__(parent)
        self._function_meta = function_meta or {}
        self._root = _FunctionItem("", "root")
        self._build_tree()

    def _build_tree(self):
        categories = {}
        for function_name, metadata in self._function_meta.items():
            category_name = metadata.get("category") or "Uncategorized"
            subcategory_name = metadata.get("sub_category")
            category = categories.setdefault(category_name, {})
            category.setdefault(subcategory_name, []).append(function_name)

        for category_name in sorted(categories, key=str.casefold):
            category_item = _FunctionItem(category_name, "category", parent=self._root)
            self._root.children.append(category_item)
            subcategories = categories[category_name]
            for subcategory_name in sorted(
                subcategories,
                key=lambda value: (value is not None, str(value).casefold()),
            ):
                parent = category_item
                if subcategory_name is not None:
                    parent = _FunctionItem(
                        subcategory_name, "subcategory", parent=category_item
                    )
                    category_item.children.append(parent)
                for function_name in sorted(
                    subcategories[subcategory_name], key=str.casefold
                ):
                    parent.children.append(
                        _FunctionItem(
                            function_name,
                            "function",
                            self._function_meta[function_name],
                            parent,
                        )
                    )

    def _item(self, index):
        if index.isValid():
            return index.internalPointer()
        return self._root

    def index(self, row, column, parent=None):
        if parent is None:
            parent = QModelIndex()
        parent_item = self._item(parent)
        if 0 <= row < len(parent_item.children):
            child = parent_item.children[row]
            return self.createIndex(row, column, child)
        return QModelIndex()

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()
        item = self._item(index).parent
        if item is None or item is self._root:
            return QModelIndex()
        return self.createIndex(item.parent.children.index(item), 0, item)

    def rowCount(self, parent=None):
        return len(self._item(parent or QModelIndex()).children)

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

        item = self._item(index)
        meta = item.metadata

        if role == Qt.ItemDataRole.DisplayRole:
            if index.column() == 0:
                return item.name
            if item.kind != "function":
                return ""
            if index.column() == 1:
                return str(meta.get("module_name", meta.get("module", "")))
            if index.column() == 2:
                return str(meta.get("description", ""))
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.ItemIsEnabled
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if self._item(index).kind == "function":
            flags |= Qt.ItemFlag.ItemIsDragEnabled
        return flags

    def mimeData(self, indexes):
        mime = QMimeData()
        if not indexes:
            return mime

        first = indexes[0]
        if first.isValid() and self._item(first).kind == "function":
            mime.setText(self._item(first).name)
        return mime

    def supportedDragActions(self):
        return Qt.DropAction.CopyAction
