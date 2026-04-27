"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import inspect
import sys
import traceback
from ast import literal_eval

from qtpy.QtWidgets import QLabel, QGroupBox
from qtpy.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QGridLayout,
    QComboBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QDialog,
    QApplication,
)

from mne_nodes.conftest import test_parameters
from mne_nodes.gui import parameter_widgets
from mne_nodes.gui.base_widgets import SimpleDict
from mne_nodes.gui.gui_utils import center
from mne_nodes.gui.parameter_widgets import Param
from mne_nodes.tests.test_parameter_widgets import gui_mapping, gui_kwargs


class ParamGuis(QWidget):
    def __init__(self):
        super().__init__()

        self.gui_dict = {}
        self.parameters = {
            key: test_parameters[value] for key, value in gui_mapping.items()
        }

        self.init_ui()

    def init_ui(self):
        test_layout = QVBoxLayout()
        for groupbox_layout in [True, False]:
            groupbox = QGroupBox(f"GroupBox Layout: {groupbox_layout}")

            grid_layout = QGridLayout()
            groupbox.setLayout(grid_layout)
            max_cols = 4
            param_names = list(self.parameters.keys())
            for idx, gui_name in enumerate(param_names):
                gui_class = getattr(parameter_widgets, gui_name, None)
                if gui_class is None:
                    print(f"Warning: No GUI class found for {gui_name}")
                    continue
                gui_parameters = list(inspect.signature(gui_class).parameters) + list(
                    inspect.signature(Param).parameters
                )
                kwargs = {
                    key: value
                    for key, value in gui_kwargs.items()
                    if key in gui_parameters
                }
                try:
                    gui = gui_class(
                        data=self.parameters,
                        name=gui_name,
                        groupbox_layout=groupbox_layout,
                        **kwargs,
                    )
                except Exception as e:
                    traceback.print_exc()
                    gui = QWidget(self)
                    layout = QVBoxLayout(gui)
                    layout.addWidget(QLabel(f"Error creating GUI for {gui_name}:\n{e}"))
                grid_layout.addWidget(gui, idx // max_cols, idx % max_cols)
                if gui_name in self.gui_dict:
                    self.gui_dict[gui_name].append(gui)
                else:
                    self.gui_dict[gui_name] = [gui]
            test_layout.addWidget(groupbox)
        set_layout = QHBoxLayout()
        self.gui_cmbx = QComboBox()
        self.gui_cmbx.addItems(list(self.gui_dict.keys()))
        set_layout.addWidget(self.gui_cmbx)

        self.set_le = QLineEdit()
        set_layout.addWidget(self.set_le)

        set_bt = QPushButton("Set")
        set_bt.clicked.connect(self.set_param)
        set_layout.addWidget(set_bt)

        show_bt = QPushButton("Show Parameters")
        show_bt.clicked.connect(self.show_parameters)
        set_layout.addWidget(show_bt)

        test_layout.addLayout(set_layout)

        self.setLayout(test_layout)

    def set_param(self):
        current_gui = self.gui_cmbx.currentText()
        try:
            value = literal_eval(self.set_le.text())
        except (SyntaxError, ValueError):
            value = self.set_le.text()
        for gui in self.gui_dict[current_gui]:
            gui.value = value

    def show_parameters(self):
        dlg = QDialog(self)
        layout = QVBoxLayout()
        layout.addWidget(SimpleDict(self.parameters))
        dlg.setLayout(layout)
        dlg.open()


if __name__ == "__main__":
    app = QApplication.instance() or QApplication(sys.argv)
    test_widget = ParamGuis()
    test_widget.show()
    center(test_widget)
    sys.exit(app.exec())
