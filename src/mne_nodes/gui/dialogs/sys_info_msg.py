"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import sys

from qtpy.QtWidgets import QDialog, QPushButton, QTextEdit, QVBoxLayout

from mne_nodes.gui.gui_utils import set_ratio_geometry


class SysInfoMsg(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        # Init layout
        layout = QVBoxLayout()
        self.show_widget = QTextEdit()
        self.show_widget.setReadOnly(True)
        layout.addWidget(self.show_widget)
        close_bt = QPushButton("Close")
        close_bt.clicked.connect(self.close)
        layout.addWidget(close_bt)
        self.setLayout(layout)
        # Connect to stdout
        stdout_stream = sys.stdout
        stdout_stream.signal.text_written.connect(self.add_text)
        # Set geometry to ratio of screen-geometry
        set_ratio_geometry(0.4, self)

    def add_text(self, text):
        self.show_widget.insertPlainText(text)
