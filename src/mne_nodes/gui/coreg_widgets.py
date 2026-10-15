"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

from qtpy.QtWidgets import QDialog

from mne_nodes.gui.widgets.list_widgets import MarkList


class CoregDialog(QDialog):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.ct = controller
        self.setWindowTitle("Coregistration Dialog")

        # Initialize UI
        self.subject_list = MarkList()

    def update_widgets(self):
        subjects = self.ct.get_datatype_items("subject")
        self.subject_list.replace_data({subject: False for subject in subjects})
