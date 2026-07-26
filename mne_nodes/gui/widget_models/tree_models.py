"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import logging

from qtpy.QtCore import QAbstractItemModel, QModelIndex, Qt


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

    def rebuild_tree(self):
        """Rebuild the internal tree from ``self._data`` and notify views."""
        self.layoutAboutToBeChanged.emit()
        self.root_item = self._build_tree(self._data)
        self.layoutChanged.emit()

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
        if parent is None:
            parent = QModelIndex()
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
        if parent is None:
            parent = QModelIndex()
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


class ShallowTreeModel(TreeModel):
    """A model for grouped ``dict[str, list]`` data with checkable keys.

    Top-level dictionary keys are displayed as parent rows and can be checked.
    List values are shown as leaf children under each key.
    """

    def __init__(self, data=None, checked=None, headers=None, parent=None):
        if checked is None:
            self._checked = []
        elif not isinstance(checked, list):
            logging.warning(
                "ShallowTreeModel expects a list for 'checked', got %s. Initializing empty list.",
                type(checked).__name__,
            )
            self._checked = []
        else:
            self._checked = checked

        super().__init__(data=data, headers=headers, parent=parent)

    def _build_tree(self, data):
        """Build a two-level tree from ``dict[str, list]`` data."""
        root = TreeItem(self._headers)

        for key, values in data.items():
            if isinstance(values, list):
                normalized_values = values
            else:
                logging.warning(
                    "ShallowTreeModel expects list values, got %s for key '%s'. Treating as empty list.",
                    type(values).__name__,
                    key,
                )
                normalized_values = []

            key_item = TreeItem([key, f"{len(normalized_values)} items"], root)
            root._children.append(key_item)

            for value in normalized_values:
                key_item._children.append(TreeItem([str(value), ""], key_item))

        return root

    def _is_checkable_key(self, index):
        if not index.isValid() or index.column() != 0:
            return False
        item = index.internalPointer()
        return item is not None and item._parent == self.root_item

    def _group_keys(self):
        return list(self._data.keys())

    def _group_key_by_row(self, row):
        group_keys = self._group_keys()
        if 0 <= row < len(group_keys):
            return group_keys[row]
        return None

    def group_key_for_index(self, index):
        """Return the top-level group key represented by ``index``."""
        if index is None or not index.isValid():
            return None

        item = index.internalPointer()
        if item is None:
            return None

        if item._parent == self.root_item:
            return self._group_key_by_row(index.row())

        parent = index.parent()
        if parent.isValid():
            return self._group_key_by_row(parent.row())
        return None

    def is_group_index(self, index):
        """Return ``True`` if index points to a top-level group row."""
        if index is None or not index.isValid():
            return False
        item = index.internalPointer()
        return item is not None and item._parent == self.root_item

    def is_item_index(self, index):
        """Return ``True`` if index points to a leaf item row."""
        if index is None or not index.isValid():
            return False
        item = index.internalPointer()
        if item is None or item._parent is None:
            return False
        return item._parent != self.root_item

    def _next_unique_group_name(self, base="__new_group"):
        n = 0
        group_name = f"{base}{n}__"
        while group_name in self._data:
            n += 1
            group_name = f"{base}{n}__"
        return group_name

    def add_group(self, key=None):
        """Add a new group key with an empty item list."""
        if key is None or str(key).strip() == "":
            key = self._next_unique_group_name()
        else:
            key = str(key)
            if key in self._data:
                key = self._next_unique_group_name(base=key)

        self._data[key] = []
        self.rebuild_tree()
        # ToDo: Somehow rowsInserted doesn't seem to be emitted here
        return key

    def remove_groups(self, keys):
        """Remove groups by key and keep ``_checked`` synchronized in place."""
        removed = []
        for key in keys:
            if key in self._data:
                self._data.pop(key)
                removed.append(key)

        if not removed:
            return []

        for key in removed:
            if key in self._checked:
                self._checked.remove(key)

        self.rebuild_tree()
        return removed

    def _next_unique_item_name(self, group_key, base="__new_item"):
        n = 0
        item_name = f"{base}{n}__"
        while item_name in self._data[group_key]:
            n += 1
            item_name = f"{base}{n}__"
        return item_name

    def add_item(self, group_key, item=None):
        """Add an item to a group list."""
        if group_key not in self._data or not isinstance(self._data[group_key], list):
            return None

        if item is None or str(item).strip() == "":
            item = self._next_unique_item_name(group_key)
        else:
            item = str(item)

        self._data[group_key].append(item)
        self.rebuild_tree()
        return item

    def remove_items(self, group_key, item_rows):
        """Remove items from a group list by their row indices."""
        if group_key not in self._data or not isinstance(self._data[group_key], list):
            return 0

        items = self._data[group_key]
        removed_count = 0
        for row in sorted(set(item_rows), reverse=True):
            if 0 <= row < len(items):
                items.pop(row)
                removed_count += 1

        if removed_count > 0:
            self.rebuild_tree()
        return removed_count

    def data(self, index, role=None):
        if role == Qt.ItemDataRole.CheckStateRole and self._is_checkable_key(index):
            key = index.internalPointer().data(0)
            return (
                Qt.CheckState.Checked
                if key in self._checked
                else Qt.CheckState.Unchecked
            )
        return super().data(index, role=role)

    def setData(self, index, value, role=None):
        if role != Qt.ItemDataRole.CheckStateRole or not self._is_checkable_key(index):
            return False

        key = index.internalPointer().data(0)
        if value in [Qt.CheckState.Checked, 2]:
            if key not in self._checked:
                self._checked.append(key)
        elif key in self._checked:
            self._checked.remove(key)

        self.dataChanged.emit(index, index)
        return True

    def flags(self, index):
        flags = super().flags(index)
        if self._is_checkable_key(index):
            flags |= Qt.ItemFlag.ItemIsUserCheckable
        return flags
