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
from mne_nodes.gui.gui_utils import edit_font, raise_user_attention, ask_user
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
        edit_font(self, 13, True)
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
        self.specific_label = TitleLabel("Specific GUI Configuration")
        layout.addWidget(self.specific_label)
        self.specific_label.hide()
        self.specific_gui_config_layout = QFormLayout()
        layout.addLayout(self.specific_gui_config_layout)
        # Initialize with appropriate gui
        gui_name = configuration.get("gui") or (
            default_type_guis.get(type(self.config.get("default")), StringGui).__name__
            if self.config.get("default") is not None
            else "StringGui"
        )
        gui_cmbx.setCurrentText(gui_name)
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
        gui = default_type_guis.get(gui_type, MultiTypeGui)(
            data=self.config, name=name, none_select=True, groupbox_layout=False
        )
        return gui

    def update_gui_config(self, gui_name):
        self.config["gui"] = gui_name
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
        if len(config_items) == 0:
            self.specific_label.hide()
        else:
            self.specific_label.show()
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
        self.editors = {}
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
        analyze_bt = QPushButton("Re-analyze Code")
        analyze_bt.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        analyze_bt.clicked.connect(self.reanalyze)
        edit_font(analyze_bt, 14)
        config_layout.addWidget(analyze_bt)
        # Add scope combobox
        scope_layout = QHBoxLayout()
        scope_layout.addWidget(TitleLabel("Scope:"))
        self.scope_cmbx = QComboBox()
        self.scope_cmbx.addItems(["subject", "group", "custom"])
        self.scope_cmbx.currentTextChanged.connect(self.update_scope)
        scope_layout.addWidget(self.scope_cmbx)
        config_layout.addLayout(scope_layout)
        # Inputs Display
        self.inputs_label = TitleLabel("Inputs:")
        config_layout.addWidget(self.inputs_label)
        # Outputs Layout
        self.outputs_label = TitleLabel("Outputs:")
        config_layout.addWidget(self.outputs_label)
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
        # ToDo Next: Complete reanalyze
        tree = ast.parse(code)
        function_defs = [
            node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
        ]
        for func in function_defs:
            if func.name not in self.func_config:
                self.func_config[func.name] = {"parameters": {}, "dependencies": []}
            start_line = func.lineno - 1
            end_line = func.end_lineno
            func_code = "\n".join(code.splitlines()[start_line:end_line])
            self.func_config[func.name]["code"] = func_code

            # Create a new tab with an editor for the function code
            editor = Editor()
            self.editors[func.name] = editor
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

            # Get parameters with defaults
            param_config = self.func_config[func.name]["parameters"]
            parameters = [a.arg for a in args[len(args) - num_defaults :]]

            # Remove old parameters if they are not longer present
            for old_param in [p for p in param_config if p not in parameters]:
                logging.info(
                    f"Parameter '{old_param}' no longer present in function '{func.name}'. Removing from configuration."
                )
                del param_config[old_param]

            # Update parameter configuration
            for i, a in enumerate(parameters):
                default = ast.literal_eval(defaults[i])
                gui = default_type_guis.get(type(default))
                if a not in param_config:
                    param_config[a] = {}
                if "default" not in param_config[a]:
                    param_config[a]["default"] = default
                if "gui" not in param_config[a]:
                    param_config[a]["gui"] = gui.__name__

            # Extract outputs from return statement
            returns = [node for node in ast.walk(func) if isinstance(node, ast.Return)]
            if len(returns) == 0:
                raise_user_attention(
                    f"No return statements found in function '{func.name}'. No outputs will be registered and this node will be a dead end.",
                    "info",
                    self,
                )
            elif len(returns) > 1:
                raise_user_attention(
                    f"Multiple return statements found in function '{func.name}'. Only the name of the first return value will be set as output. This may lead to unexpected behavior.",
                    "warning",
                    self,
                )
            ret = returns[0]
            if isinstance(ret.value, ast.Tuple):
                for val in ret.value.elts:
                    if not isinstance(val, ast.name):
                        raise_user_attention(
                            f"Return value in function '{func.name}' is not a name. Only constant return values are supported currently.",
                            "warning",
                            self,
                        )
                        return
                self.func_config[func.name]["outputs"] = [e.id for e in ret.value.elts]
            elif isinstance(ret.value, ast.Name):
                self.func_config[func.name]["outputs"] = [ret.value.id]
            else:
                raise_user_attention(
                    f"Return value in function '{func.name}' is not a name or tuple of names. Only constant return values are supported currently.",
                    "warning",
                    self,
                )
        # Update parameter configuration
        self.update_config(self.tab_widget.currentIndex())

    def reanalyze(self):
        # Get code from editors
        code = self.get_code()
        # Clear editor tabs
        for idx in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(idx)
            widget.deleteLater()
        self.tab_widget.clear()
        self.analyze_code(code)

    def update_config(self, idx):
        self.current_func = list(self.func_config.keys())[idx]
        # Update inputs/outputs labels
        self.inputs_label.setText(
            f"Inputs: {','.join(self.func_config[self.current_func]['inputs'])}"
        )
        self.outputs_label.setText(
            f"Outputs: {','.join(self.func_config[self.current_func]['outputs'])}"
        )
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

    def get_code(self):
        code = ""
        for func_name, editor in self.editors.items():
            code += editor.toPlainText() + "\n\n"
            self.func_config[func_name]["code"] = editor.toPlainText()
        return code

    def param_configuration(self, param_name):
        # Passing the configuration dict works since ParameterWidgets will fill
        # the existing container.
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

    def closeEvent(self, event):
        # Update the code in the configuration before closing
        for func_name, editor in self.editors.items():
            self.func_config[func_name]["code"] = editor.toPlainText()
        # Check for mandatory configuration items
        warning_msg = "The following mandatory configuration items are missing:\n"
        ok = True
        for func_name, func_config in self.func_config.items():
            # Check function
            if len(func_config.get("outputs", [])) == 0:
                warning_msg += f"Function '{func_name}' has no outputs defined.\n"
                ok = False
            elif len(func_config.get("inputs", [])) == 0:
                logging.warning(f"Function '{func_name}' has no inputs defined.")
                ok = False
            # Check parameters
            for param_name, param_config in func_config["parameters"].items():
                if "default" not in param_config:
                    warning_msg += f"Parameter '{param_name}' in function '{func_name}' has no default value defined.\n"
                    ok = False
        if ok:
            event.accept()
        else:
            warning_msg += "Do you want to close anyway?"
            ans = ask_user(warning_msg, parent=self)
            if ans:
                event.accept()
            event.ignore()
