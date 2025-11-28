"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import ast
import inspect
import logging

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
    QLayout,
    QSizePolicy,
    QTabWidget,
    QLineEdit,
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


class Editor(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFont(QFont("Consolas", 12))
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))
        self.highlighter = FunctionHighlighter(self.document())


class ParameterConfiguration(QDialog):
    def __init__(self, param_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Configure Parameter: {param_name}")
        layout = QFormLayout(self)
        self.setLayout(layout)
        # GUI selection
        gui_cmbx = QComboBox()
        gui_cmbx.addItems([gui.__name__ for gui in parameter_guis])
        gui_cmbx.currentTextChanged.connect(self.update_gui_config)
        layout.addRow("GUI Type", gui_cmbx)
        # GUI config
        self.gui_config_layout = QFormLayout()
        layout.addRow("GUI Configuration", self.gui_config_layout)
        # Add widgets for parameter configuration here
        self.default_edit = QLineEdit()
        layout.addRow("Default", self.default_edit)

    def update_gui_config(self, gui_name):
        gui = globals()[gui_name]
        signature = inspect.signature(gui)
        print(signature)


class FunctionImporter(QDialog):
    def __init__(self, controller, code, parent=None):
        super().__init__(parent)
        # Attributes
        self.controller = controller
        self.funcs = {}
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
        scope_layout.setSizeConstraints(
            QLayout.SizeConstraint.SetMinimumSize, QLayout.SizeConstraint.SetMinimumSize
        )
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
        # Add (optional) dependency configuration
        # Add input configuration
        self.input_button = QPushButton("Select Inputs")
        self.input_button.clicked.connect(self.select_inputs)
        edit_font(self.input_button, 14)
        self.input_button.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum
        )
        config_layout.addWidget(self.input_button)
        self.parameter_title = TitleLabel("Configure Parameters")
        config_layout.addWidget(self.parameter_title)
        # Add parameter configuration
        self.parameter_layout = QFormLayout()
        self.parameter_layout.setSizeConstraints(
            QLayout.SizeConstraint.SetDefaultConstraint,
            QLayout.SizeConstraint.SetMinimumSize,
        )
        config_layout.addLayout(self.parameter_layout)
        config_layout.addStretch()

        # Analyze the code and populate the UI
        self.analyze_code(code)

        self.show()

    def analyze_code(self, code):
        # Analyze the code to extract inputs and parameters
        tree = ast.parse(code)
        function_defs = [
            node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
        ]
        for func in function_defs:
            self.funcs[func.name] = {"param_config": {}, "dependencies": []}
            start_line = func.lineno - 1
            end_line = func.end_lineno
            func_code = "\n".join(code.splitlines()[start_line:end_line])
            self.funcs[func.name]["code"] = func_code
            # Create a new tab for the function code
            editor = Editor()
            editor.setPlainText(func_code)
            self.tab_widget.addTab(editor, func.name)
            # Extract inputs and parameters from function arguments
            args = func.args.args
            defaults = func.args.defaults
            num_defaults = len(defaults)
            self.funcs[func.name]["args"] = [a.arg for a in args]
            self.funcs[func.name]["inputs"] = [
                a.arg for a in args[: len(args) - num_defaults]
            ]
            self.funcs[func.name]["params"] = [
                a.arg for a in args[len(args) - num_defaults :]
            ]
            self.funcs[func.name]["defaults"] = {
                a.arg: defaults[i].value
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
                self.funcs[func.name]["outputs"] = [e.id for e in ret.value.elts]  # type: ignore[attr-defined]
            else:
                self.funcs[func.name]["outputs"] = [ret.value.id]  # type: ignore[attr-defined]
        # Select the first function by default
        self.update_config(0)

    def update_config(self, idx):
        # Update the configuration based on the loaded function
        self.current_func = list(self.funcs.keys())[idx]
        # Remove existing parameter widgets
        for i in reversed(range(self.parameter_layout.count())):
            widget = self.parameter_layout.itemAt(i).widget()
            if widget is not None and widget != self.parameter_title:
                self.parameter_layout.removeWidget(widget)
                widget.deleteLater()
        # Add parameter widgets
        for param, default in self.funcs[self.current_func]["params"].items():
            param_bt = QPushButton(qta.icon("fa5s.cog"))
            param_bt.clicked.connect(lambda: ParameterConfiguration(param, parent=self))
            self.parameter_layout.addRow(param, param_bt)

    def update_scope(self, text):
        if text == "custom":
            self.dependency_bt.show()
        else:
            self.dependency_bt.hide()

    def select_inputs(self):
        # Open a dialog to select inputs
        args = self.funcs[self.current_func]["args"]
        inputs = self.funcs[self.current_func]["inputs"]
        input_list = CheckList(args, inputs, ui_button_pos="bottom")
        SimpleDialog(input_list, parent=self, title="Select Inputs", modal=True)
        self.funcs[self.current_func]["params"] = [a for a in args if a not in inputs]

    def manage_dependencies(self):
        # Open a dialog to manage dependencies
        dep_list = CheckList(
            self.controller.data_types,
            self.funcs[self.current_func]["dependencies"],
            ui_button_pos="bottom",
        )
        SimpleDialog(dep_list, parent=self, title="Select Dependencies", modal=True)
