"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

from qtpy.QtWidgets import QDialog, QTextEdit, QVBoxLayout

from mne_nodes.gui.gui_utils import set_ratio_geometry


# ToDo:Rewrite About Dialog (maybe automatic copy from README.md with setMarkdown)
class AboutDialog(QDialog):
    def __init__(self, main_win):
        super().__init__(main_win)
        self.mw = main_win
        # with open(resources.files("mne_nodes.resources") / "license.txt") as file:
        #     license_text = file.read()
        # license_text = license_text.replace("\n", "<br>")
        text = (
            "<h1>MNE-Pipeline HD</h1>"
            "<b>A Pipeline-GUI for MNE-Python</b><br>"
            "(originally developed for MEG-Lab Heidelberg)<br>"
            "<i>Development was initially inspired by: "
            "<a href=https://doi.org/10.3389/fnins.2018.00006>Andersen "
            "L.M. 2018</a></i><br>"
            "<br>"
            "As for now, this program is still in alpha-state, "
            "so some features may not work as expected. "
            "Be sure to check all the parameters for each step "
            "to be correctly adjusted to your needs.<br>"
            "<br>"
            "<b>Developed by:</b><br>"
            "Martin Schulz (medical student, Heidelberg)<br>"
            "<br>"
            "<b>Dependencies:</b><br>"
            "MNE-Python: <a href=https://github.com/mne-tools/"
            "mne-python>Website</a>"
            "<a href=https://github.com/mne-tools/mne-python>"
            "GitHub</a><br>"
            "<a href=https://github.com/5yutan5/PyQtDarkTheme>"
            "pyqtdarktheme</a><br>"
            "<br>"
            # "<b>Licensed under:</b><br>" + license_text
        )

        layout = QVBoxLayout()

        text_widget = QTextEdit()
        text_widget.setReadOnly(True)
        text_widget.setHtml(text)
        layout.addWidget(text_widget)

        self.setLayout(layout)
        set_ratio_geometry((0.25, 0.9), self)
