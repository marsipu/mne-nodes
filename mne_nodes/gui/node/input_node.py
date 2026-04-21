"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import mne_bids
from PySide6.QtWidgets import QPushButton
from mne_nodes.gui.gui_utils import get_user_input
from qtpy.QtWidgets import QWidget, QComboBox, QVBoxLayout
from mne_bids import BIDSPath, get_datatypes

from mne_nodes.gui.base_widgets import CheckListProgress, ShallowTreeWidget
from mne_nodes.gui.node.base_node import BaseNode


class InputWidget(QWidget):
    def __init__(self, ct, **kwargs):
        super().__init__(**kwargs)
        self.ct = ct
        self.bp = BIDSPath(ct.bids_root)
        self.list_widget = None
        self.setLayout(QVBoxLayout())

        # Initialize Widgets
        self.root_bt = QPushButton("Set BIDS Root Directory")
        self.root_bt.clicked.connect(self.set_root)
        self.group_cmbx = QComboBox()
        self.group_cmbx.addItems(
            ["file", "subject", "session", "run", "task", "custom"]
        )
        self.group_cmbx.currentTextChanged.connect(self.cmbx_changed)
        self.layout().addWidget(self.group_cmbx)

    def set_root(self):
        new_root = get_user_input(
            "Select BIDS root directory", "folder", cancel_allowed=True
        )
        if new_root is not None:
            self.ct.bids_root = new_root

    def cmbx_changed(self, group_by):
        # Remove old widget
        if self.list_widget is not None:
            self.layout().removeWidget(self.list_widget)
            self.list_widget.deleteLater()
        data = mne_bids.get_entity_vals(self.ct.bids_root, group_by)
        if group_by not in self.ct.selected_inputs:
            self.ct.selected_inputs[group_by] = []
        if group_by == "custom":
            data = self.ct.get("custom_groups")
            self.list_widget = ShallowTreeWidget(
                data,
                checked=self.ct.selected_inputs[group_by],
                headers=["Group Name", "Subjects"],
            )
        else:
            self.list_widget = CheckListProgress(
                data, checked=self.ct.selected_inputs[group_by]
            )
        # Always save to the config the latest input selection
        self.list_widget.checkedChanged.connect(self.save_input_selection)
        self.layout().addWidget(self.list_widget)

    def save_input_selection(self):
        self.ct.set("selected_inputs", self.ct.selected_inputs)


class InputNode(BaseNode):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Set name to dataset name if available
        dataset_name = self.ct.get_dataset_name()
        if dataset_name is not None:
            self.name = dataset_name

        # Add input widget
        self.input_widget = InputWidget(self.ct)
        self.add_widget(self.input_widget)

        # Add data-types as outputs
        data_types = get_datatypes(self.ct.bids_root)
        for dt in data_types:
            self.add_output(dt, multi_connection=True)
