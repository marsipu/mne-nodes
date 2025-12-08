"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import ast
import inspect
import logging
from functools import partial
from types import UnionType, NoneType
from typing import get_args

import qtawesome as qta
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QFormLayout,
    QVBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QPlainTextEdit,
    QSizePolicy,
    QTabWidget,
)
from mne_nodes.gui.base_widgets import SimpleDialog, CheckList
from mne_nodes.gui.code_editor import PythonHighlighter
from mne_nodes.gui.gui_utils import edit_font
from mne_nodes.gui.parameter_widgets import (
    IntGui,
    FloatGui,
    StringGui,
    FuncGui,
    BoolGui,
    DualTupleGui,
    ComboGui,
    ListGui,
    CheckListGui,
    DictGui,
    SliderGui,
    MultiTypeGui,
    LabelGui,
    ColorGui,
    PathGui,
    Param,
)

parameter_guis = [
    IntGui,
    FloatGui,
    StringGui,
    FuncGui,
    BoolGui,
    DualTupleGui,
    ComboGui,
    ListGui,
    CheckListGui,
    DictGui,
    SliderGui,
    MultiTypeGui,
    LabelGui,
    ColorGui,
    PathGui,
]

default_type_guis = {
    int: IntGui,
    float: FloatGui,
    str: StringGui,
    bool: BoolGui,
    list: ListGui,
    dict: DictGui,
    object: MultiTypeGui,
}


class TitleLabel(QLabel):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        edit_font(self, 14, True)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)


class FunctionHighlighter(PythonHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.n_args = 0
        # Additional highlighting rules can be added here
        # ToDo: Highlight function arguments in different colors


class Editor(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFont(QFont("Consolas", 12))
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))
        self.highlighter = FunctionHighlighter(self.document())


class ParameterConfiguration(QDialog):
    def __init__(self, param_name, configuration, parent=None):
        super().__init__(parent)
        self.config = configuration
        self.setWindowTitle(f"Configure Parameter: {param_name}")
        layout = QVBoxLayout(self)
        # GUI selection
        selection_layout = QHBoxLayout()
        selection_layout.addWidget(TitleLabel("Select GUI:"))
        gui_cmbx = QComboBox()
        gui_cmbx.addItems([gui.__name__ for gui in parameter_guis])
        gui_cmbx.currentTextChanged.connect(self.update_gui_config)
        selection_layout.addWidget(gui_cmbx)
        layout.addLayout(selection_layout)
        # GUI config
        layout.addWidget(TitleLabel("GUI Configuration"))
        base_params = {
            name: {"default": param.default, "annotation": param.annotation}
            for name, param in inspect.signature(Param).parameters.items()
            if param.default != inspect.Parameter.empty
        }
        for name, param in base_params.items():
            gui = self._get_type_gui(name, param)
            if gui is not None:
                layout.addWidget(gui)
        # Specific GUI config
        layout.addWidget(TitleLabel("Specific GUI Configuration"))
        self.specific_gui_config_layout = QFormLayout()
        layout.addLayout(self.specific_gui_config_layout)
        # Initialize with the first GUI
        self.update_gui_config(gui_cmbx.currentText())
        self.open()

    def _get_type_gui(self, name, param):
        # Get type for gui configuration items
        # ToDo Next: Implement MultiTypeGui
        if param["annotation"] is inspect.Parameter.empty:
            logging.warning(f"No type annotation for parameter '{name}'. Skipping.")
            return None
        elif (
            type(param["annotation"]) is UnionType
        ):  # alias for typing.Union since Python 3.14
            logging.info(
                f"UnionType annotation for parameter '{name}'. Using first not NoneType as type."
            )
            args = get_args(param["annotation"])
            gui_type = next((arg for arg in args if arg is not NoneType), str)
        else:
            gui_type = param["annotation"]
        gui = default_type_guis.get(gui_type, StringGui)(
            data=self.config, name=name, none_select=True, groupbox_layout=False
        )
        return gui

    def update_gui_config(self, gui_name):
        # Remove existing specific gui config widgets
        for i in reversed(range(self.specific_gui_config_layout.count())):
            widget = self.specific_gui_config_layout.itemAt(i).widget()
            if widget is not None:
                self.specific_gui_config_layout.removeWidget(widget)
                widget.deleteLater()
        # Add new specific gui config widgets
        gui_class = globals()[gui_name]
        config_items = {
            name: {"default": param.default, "annotation": param.annotation}
            for name, param in inspect.signature(gui_class).parameters.items()
            if param.default != inspect.Parameter.empty
        }
        for name, param in config_items.items():
            gui = self._get_type_gui(name, param)
            if gui is not None:
                self.specific_gui_config_layout.addRow(name, gui)


class FunctionImporter(QDialog):
    def __init__(self, controller, code, parent=None):
        super().__init__(parent)
        # Attributes
        self.controller = controller
        self.func_config = {}
        self.current_func = None
        # UI
        layout = QHBoxLayout(self)
        self.setWindowTitle("Import Function")
        # Init code editor tabs
        self.tab_widget = QTabWidget()
        self.tab_widget.tabBarClicked.connect(self.update_config)
        self.tab_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        layout.addWidget(self.tab_widget)
        # Init configuration
        config_layout = QVBoxLayout()
        layout.addLayout(config_layout)
        # Add scope combobox
        scope_layout = QHBoxLayout()
        scope_layout.addWidget(TitleLabel("Scope:"))
        self.scope_cmbx = QComboBox()
        self.scope_cmbx.addItems(["subject", "group", "custom"])
        self.scope_cmbx.currentTextChanged.connect(self.update_scope)
        scope_layout.addWidget(self.scope_cmbx)
        config_layout.addLayout(scope_layout)
        # (optional) dependency button when scope is "Custom"
        self.dependency_bt = QPushButton("Manage Dependencies")
        self.dependency_bt.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum
        )
        self.dependency_bt.clicked.connect(self.manage_dependencies)
        edit_font(self.dependency_bt, 14)
        config_layout.addWidget(self.dependency_bt)
        self.dependency_bt.hide()
        self.parameter_title = TitleLabel("Configure Parameters")
        config_layout.addWidget(self.parameter_title)
        # Add parameter configuration
        self.parameter_layout = QFormLayout()
        self.parameter_layout.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint
        )
        self.parameter_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.parameter_layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft)
        config_layout.addLayout(self.parameter_layout)
        config_layout.addStretch()

        # Analyze the code and populate the UI
        self.analyze_code(code)

        self.open()

    def analyze_code(self, code):
        # Analyze the code to extract inputs and parameters
        tree = ast.parse(code)
        function_defs = [
            node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
        ]
        for func in function_defs:
            self.func_config[func.name] = {"parameters": {}, "dependencies": []}
            start_line = func.lineno - 1
            end_line = func.end_lineno
            func_code = "\n".join(code.splitlines()[start_line:end_line])
            self.func_config[func.name]["code"] = func_code
            # Create a new tab for the function code
            editor = Editor()
            editor.setPlainText(func_code)
            self.tab_widget.addTab(editor, func.name)
            # Extract inputs and parameters from function arguments
            args = func.args.args
            defaults = func.args.defaults
            num_defaults = len(defaults)
            # Split args into inputs and parameters
            self.func_config[func.name]["inputs"] = [
                a.arg for a in args[: len(args) - num_defaults]
            ]
            self.func_config[func.name]["parameters"] = {
                a.arg: {"default": ast.literal_eval(defaults[i])}
                for i, a in enumerate(args[len(args) - num_defaults :])
            }  # type: ignore[attr-defined]

            # Extract outputs from return statement
            returns = [node for node in ast.walk(func) if isinstance(node, ast.Return)]
            if len(returns) == 0:
                logging.info(
                    f"No return statements found in function '{func.name}'. No outputs will be registered and this node will be a dead end."
                )
            elif len(returns) > 1:
                logging.warning(
                    f"Multiple return statements found in function '{func.name}'. Only the first one will be set as output. This is not supported and may lead to unexpected behavior."
                )
            ret = returns[0]
            if isinstance(ret.value, ast.Tuple):
                self.func_config[func.name]["outputs"] = [e.id for e in ret.value.elts]  # type: ignore[attr-defined]
            else:
                self.func_config[func.name]["outputs"] = [ret.value.id]  # type: ignore[attr-defined]
        # Select the first function by default
        self.update_config(0)

    def update_config(self, idx):
        # Update the configuration based on the loaded function
        self.current_func = list(self.func_config.keys())[idx]
        # Remove existing parameter widgets
        for i in reversed(range(self.parameter_layout.count())):
            widget = self.parameter_layout.itemAt(i).widget()
            if widget is not None and widget != self.parameter_title:
                self.parameter_layout.removeWidget(widget)
                widget.deleteLater()
        # Add parameter widgets
        for param in self.func_config[self.current_func]["parameters"]:
            param_bt = QPushButton()
            param_bt.setSizePolicy(
                QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum
            )
            param_bt.setIcon(qta.icon("fa5s.cog"))
            param_bt.clicked.connect(partial(self.param_configuration, param))
            self.parameter_layout.addRow(param, param_bt)

    def update_scope(self, text):
        if text == "custom":
            self.dependency_bt.show()
        else:
            self.dependency_bt.hide()

    def param_configuration(self, param_name):
        config = self.func_config[self.current_func]["parameters"][param_name]
        ParameterConfiguration(param_name, config, parent=self)

    def manage_dependencies(self):
        # Open a dialog to manage dependencies
        dep_list = CheckList(
            self.controller.data_types,
            self.func_config[self.current_func]["dependencies"],
            ui_button_pos="bottom",
        )
        SimpleDialog(dep_list, parent=self, title="Select Dependencies", modal=True)
