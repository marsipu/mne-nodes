"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import inspect
import sys
import traceback
from ast import literal_eval

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

from mne_nodes.gui import parameter_widgets
from mne_nodes.gui.base_widgets import SimpleDict
from mne_nodes.gui.parameter_widgets import Param
from mne_nodes.tests.test_parameter_widgets import gui_mapping, gui_kwargs

parameters = {
    "int": 1,
    "float": 5.3,
    "string": "postcentral-lh",
    "multi_type": 42,
    "func": "np.arange(10) * np.pi",
    "bool": True,
    "tuple": (45, 6),
    "combo": "b",
    "list": [1, 454.33, "postcentral-lh", 5],
    "check_list": ["postcentral-lh"],
    "dict": {"A": "B", "C": 58.144, 3: [1, 2, 3, 4], "D": {"A": 1, "B": 2}},
    "slider": 5,
    "color": {"C": "#98765432", "3": "#97867564"},
    "path": "C:/test",
}


class ParamGuis(QWidget):
    def __init__(self):
        super().__init__()

        self.gui_dict = {}

        self.init_ui()

    def init_ui(self):
        global parameters
        test_layout = QVBoxLayout()
        grid_layout = QGridLayout()
        max_cols = 4
        parameters = {key: parameters[value] for key, value in gui_mapping.items()}
        param_names = list(parameters.keys())
        for idx, gui_name in enumerate(param_names):
            gui_class = getattr(parameter_widgets, gui_name)
            gui_parameters = list(inspect.signature(gui_class).parameters) + list(
                inspect.signature(Param).parameters
            )
            kwargs = {
                key: value for key, value in gui_kwargs.items() if key in gui_parameters
            }
            gui = gui_class(data=parameters, name=gui_name, **kwargs)
            grid_layout.addWidget(gui, idx // max_cols, idx % max_cols)
            self.gui_dict[gui_name] = gui

        test_layout.addLayout(grid_layout)

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
        parameters[current_gui] = value
        p_gui = self.gui_dict[current_gui]
        p_gui.read_param()
        p_gui._set_param()
        print(traceback.format_exc())

    def show_parameters(self):
        dlg = QDialog(self)
        layout = QVBoxLayout()
        layout.addWidget(SimpleDict(parameters))
        dlg.setLayout(layout)
        dlg.open()


if __name__ == "__main__":
    app = QApplication.instance() or QApplication(sys.argv)
    test_widget = ParamGuis()
    test_widget.show()
    sys.exit(app.exec())
