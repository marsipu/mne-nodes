"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import logging
import sys
from collections import Counter
from importlib import resources
from pathlib import Path

from qtpy.QtWidgets import (
    QDialog,
    QGridLayout,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QApplication,
    QSizePolicy,
)

from mne_nodes import extra
from mne_nodes.gui.base_widgets import SimpleList
from mne_nodes.gui.gui_utils import set_ratio_geometry
from mne_nodes.pipeline.legacy import MEEG


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
        sys.stdout.signal.text_written.connect(self.add_text)
        # Set geometry to ratio of screen-geometry
        set_ratio_geometry(0.4, self)
        self.show()

    def add_text(self, text):
        self.show_widget.insertPlainText(text)


# ToDo: Rewrite
class RawInfo(QDialog):
    def __init__(self, main_win):
        super().__init__(main_win)
        self.mw = main_win
        self.info_string = None

        set_ratio_geometry(0.6, self)

        self.init_ui()
        self.open()

    def init_ui(self):
        layout = QGridLayout()
        meeg_list = SimpleList(self.mw.ct.pr.all_meeg)
        meeg_list.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred
        )
        meeg_list.currentChanged.connect(self.meeg_selected)
        layout.addWidget(meeg_list, 0, 0)

        self.info_label = QTextEdit()
        self.info_label.setReadOnly(True)
        self.info_label.setSizePolicy(
            QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.MinimumExpanding
        )
        layout.addWidget(self.info_label, 0, 1)

        close_bt = QPushButton("Close")
        close_bt.clicked.connect(self.close)
        layout.addWidget(close_bt, 1, 0, 1, 2)

        self.setLayout(layout)

    # ToDo: Just parse/reformat repr(info) instead of rewriting all keys
    def meeg_selected(self, meeg_name):
        # Get size in Mebibytes of all files associated to this
        meeg = MEEG(meeg_name, self.mw.ct)
        info = meeg.load_info()
        fp = meeg.file_parameters
        meeg.get_existing_paths()
        other_infos = {}

        sizes = []
        for path_type in meeg.existing_paths:
            for path in meeg.existing_paths[path_type]:
                file_name = Path(path).name
                if file_name in fp and "SIZE" in fp[file_name]:
                    sizes.append(fp[file_name]["SIZE"])
        other_infos["no_files"] = len(sizes)

        sizes_sum = sum(sizes)
        if sizes_sum / 1024 < 1000:
            other_infos["size"] = f"{int(sizes_sum / 1024)}"
            size_unit = "KB"
        else:
            other_infos["size"] = f"{int(sizes_sum / 1024**2)}"
            size_unit = "MB"

        ch_type_counter = Counter(info.get_channel_types())
        other_infos["ch_types"] = ", ".join(
            [f"{key}: {value}" for key, value in ch_type_counter.items()]
        )

        key_list = [
            ("no_files", "Number associated files"),
            ("size", "Size of all associated files", size_unit),
            ("proj_name", "Project-Name"),
            ("experimenter", "Experimenter"),
            ("line_freq", "Powerline-Frequency", "Hz"),
            ("sfreq", "Samplerate", "Hz"),
            ("highpass", "Highpass", "Hz"),
            ("lowpass", "Lowpass", "Hz"),
            ("nchan", "Number of channels"),
            ("ch_types", "Channel-Types"),
            ("subject_info", "Subject-Info"),
            ("device_info", "Device-Info"),
            ("helium_info", "Helium-Info"),
        ]

        self.info_string = f"<h1>{meeg_name}</h1>"

        for key_tuple in key_list:
            key = key_tuple[0]
            if key in info:
                value = info[key]
            elif key in other_infos:
                value = other_infos[key]
            else:
                value = None

            if len(key_tuple) == 2:
                self.info_string += f"<b>{key_tuple[1]}:</b> {value}<br>"
            else:
                self.info_string += (
                    f"<b>{key_tuple[1]}:</b> {value} <i>{key_tuple[2]}</i><br>"
                )

        self.info_label.setHtml(self.info_string)


# ToDo:Rewrite About Dialog (maybe automatic copy from README.md with setMarkdown)
class AboutDialog(QDialog):
    def __init__(self, main_win):
        super().__init__(main_win)
        self.mw = main_win
        with open(resources.files(extra) / "license.txt") as file:
            license_text = file.read()
        license_text = license_text.replace("\n", "<br>")
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
            "<b>Licensed under:</b><br>" + license_text
        )

        layout = QVBoxLayout()

        text_widget = QTextEdit()
        text_widget.setReadOnly(True)
        text_widget.setHtml(text)
        layout.addWidget(text_widget)

        self.setLayout(layout)
        set_ratio_geometry((0.25, 0.9), self)
        self.open()


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

        if parent:
            self.open()
        else:
            self.exec()

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
        ErrorDialog(exc_str, title="A unexpected error occurred")
    else:
        logging.debug("No QApplication instance available.")
