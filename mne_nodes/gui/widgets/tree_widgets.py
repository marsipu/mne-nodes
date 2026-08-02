"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import logging

from qtpy.QtCore import Qt, Signal
from qtpy.QtGui import QFont
from qtpy.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTreeView,
    QVBoxLayout,
)

from mne_nodes.gui.gui_utils import get_user_input
from mne_nodes.gui.widget_models.tree_models import ShallowTreeModel, TreeModel
from mne_nodes.gui.widgets.base import Base
from mne_nodes.pipeline.settings import Settings


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
