"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import mne_bids
from PySide6.QtWidgets import QWidget, QComboBox, QVBoxLayout
from mne_bids import BIDSPath

from mne_nodes.gui.base_widgets import CheckListProgress
from mne_nodes.gui.node.base_node import BaseNode


class InputWidget(QWidget):
    def __init__(self, ct, **kwargs):
        super().__init__(**kwargs)
        self.ct = ct
        self.bp = BIDSPath(ct.bids_root)
        self.list_widget = None
        self.setLayout(QVBoxLayout())

        group_bys = ["file", "subject", "session", "run", "task"]

        # Initialize Widgets
        self.group_cmbx = QComboBox()
        self.group_cmbx.addItems(group_bys)
        self.group_cmbx.currentTextChanged.connect(self.cmbx_changed)
        self.layout().addWidget(self.group_cmbx)

    def cmbx_changed(self, group_by):
        # Remove old widget
        if self.list_widget is not None:
            self.layout().removeWidget(self.list_widget)
            self.list_widget.deleteLater()
        data = mne_bids.get_entity_vals(self.ct.bids_root, group_by)
        if group_by not in self.ct.selected_inputs:
            self.ct.selected_inputs[group_by] = []
        self.list_widget = CheckListProgress(data, self.ct.selected_inputs[group_by])
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
