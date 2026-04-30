"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import logging
import sys

from mne_nodes.gui.gui_utils import set_ratio_geometry
from qtpy.QtWidgets import QDialog, QPushButton, QTextEdit, QVBoxLayout, QApplication


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


# ToDo:Rewrite About Dialog (maybe automatic copy from README.md with setMarkdown)
class AboutDialog(QDialog):
    def __init__(self, main_win):
        super().__init__(main_win)
        self.mw = main_win
        # with open(resources.files(extra) / "license.txt") as file:
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


class ErrorDialog(QDialog):
    def __init__(self, exception_tuple, parent=None, title=None):
        if parent:
            super().__init__(parent)
        else:
            super().__init__()
        self.err = exception_tuple
        self.title = title
        if self.title:
            self.setWindowTitle(self.title)
        else:
            self.setWindowTitle("An Error ocurred!")

        set_ratio_geometry(0.6, self)

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        self.display = QTextEdit()
        self.display.setLineWrapMode(QTextEdit.WidgetWidth)
        self.display.setReadOnly(True)
        self.formated_tb_text = self.err[2].replace("\n", "<br>")
        if self.title:
            self.html_text = (
                f"<h1>{self.title}</h1><h2>{self.err[1]}</h2>{self.formated_tb_text}"
            )
        else:
            self.html_text = f"<h1>{self.err[1]}</h1>{self.formated_tb_text}"
        self.display.setHtml(self.html_text)
        layout.addWidget(self.display)

        self.close_bt = QPushButton("Close")
        self.close_bt.clicked.connect(self.close)
        layout.addWidget(self.close_bt)

        self.setLayout(layout)


def show_error_dialog(exc_str):
    """Checks if a QApplication instance is available and shows the Error-
    Dialog.

    If unavailable (non-console application), log an additional notice.
    """
    if QApplication.instance() is not None:
        ErrorDialog(exc_str, title="A unexpected error occurred").exec()
    else:
        logging.debug("No QApplication instance available.")
