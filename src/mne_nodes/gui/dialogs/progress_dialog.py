"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import time

from qtpy.QtWidgets import QApplication, QDialog, QLabel, QProgressBar, QVBoxLayout


class ProgressDialog(QDialog):
    def __init__(self, text, maximum=100, parent=None, update_interval_ms=50):
        super().__init__(parent)

        self.update_interval_s = update_interval_ms / 1000
        self.last_update = time.monotonic() - self.update_interval_s

        layout = QVBoxLayout()

        self.label = QLabel(text)
        layout.addWidget(self.label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, maximum)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.setLayout(layout)

    def set_value(self, value):
        now = time.monotonic()
        if value == self.progress_bar.maximum() or (
            now - self.last_update >= self.update_interval_s
        ):
            self.progress_bar.setValue(value)
            self.last_update = now
            QApplication.processEvents()
