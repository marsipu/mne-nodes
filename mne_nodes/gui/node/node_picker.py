"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

from qtpy.QtWidgets import QDockWidget, QTabWidget


class NodePicker(QDockWidget):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.ct = controller
        self.tab_widget = QTabWidget()
        self.setWindowTitle("Node Picker")
        self.setGeometry(100, 100, 300, 200)
        self.setWidget(self.tab_widget)
