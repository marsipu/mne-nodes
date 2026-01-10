"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

from PySide6.QtWidgets import QWidget, QComboBox, QVBoxLayout
from mne_bids import BIDSPath

from mne_nodes.gui.base_widgets import CheckList
from mne_nodes.gui.node.base_node import BaseNode


class InputWidget(QWidget):
    def __init__(self, ct, **kwargs):
        super().__init__(**kwargs)
        self.ct = ct
        self.bp = BIDSPath(ct.bids_root)

        self.setLayout(QVBoxLayout())

        group_bys = ["file", "subject", "session", "run", "task"]

        # Initialize Widgets
        self.group_cmbx = QComboBox()
        self.group_cmbx.addItems(group_bys)
        self.group_cmbx.currentTextChanged.connect(self.cmbx_changed)
        self.layout().addWidget(self.group_cmbx)

    def cmbx_changed(self, group_by):
        if self.list_widget is not None:
            self.layout().removeWidget(self.list_widget)
            self.list_widget.deleteLater()
        self.list_widget = CheckList()


class InputNode(BaseNode):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Set name to dataset name if available
        dataset_name = self.ct.get_dataset_name()
        if dataset_name is not None:
            self.name = dataset_name
