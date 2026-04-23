"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import ast
import inspect
import logging
from functools import partial
from os import PathLike
from os.path import isfile
from types import UnionType, NoneType
from typing import get_args, get_type_hints, get_origin, Union

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
    QWidget,
)
from mne_nodes.gui.code_editor import PythonHighlighter
from mne_nodes.gui.dialogs import ErrorDialog
from mne_nodes.gui.gui_utils import (
    edit_font,
    raise_user_attention,
    ask_user,
    get_user_input,
)
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
from mne_nodes.pipeline.exception_handling import get_exception_tuple

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
    "int": IntGui,
    "float": FloatGui,
    "str": StringGui,
    "bool": BoolGui,
    "list": ListGui,
    "dict": DictGui,
    "object": MultiTypeGui,
    "NoneType": MultiTypeGui,
    "tuple": DualTupleGui,
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
        self.n_args = 0  # Additional highlighting rules can be added here  # ToDo: Highlight function arguments in different colors


class Editor(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFont(QFont("Consolas", 12))
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))
        self.highlighter = FunctionHighlighter(self.document())
        self.setMinimumSize(600, 400)


class InputConfiguration(QDialog):
    def __init__(self, input_name, configuration, parent=None):
        super().__init__(parent)
        self.config = configuration
        self.setWindowTitle(f"Configure Input: {input_name}")
        layout = QVBoxLayout(self)
        layout.addWidget(
            BoolGui(
                data=configuration,
                name="optional",
                none_select=False,
                groupbox_layout=False,
            )
        )
        layout.addWidget(
            ListGui(
                data=configuration,
                name="accepted",
                alias="Accepted connections",
                none_select=False,
                groupbox_layout=False,
                show_edit_bt=False,
            )
        )
        self.open()


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
        excluded_params = ["function_name", "parent_widget"]
        layout.addWidget(TitleLabel("GUI Configuration"))
        base_params = {
            name: {"default": param.default, "annotation": param.annotation}
            for name, param in inspect.signature(Param).parameters.items()
            if param.default != inspect.Parameter.empty and name not in excluded_params
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
            default_type_guis.get(
                type(self.config.get("default").__name__), StringGui
            ).__name__
            if self.config.get("default") is not None
            else "StringGui"
        )
        gui_cmbx.setCurrentText(gui_name)
        self.open()

    def _get_type_gui(self, name, param):
        # Get type for gui configuration items
        # ToDo Next: Refine recognition (none_select etc.) and remove them from parameter-config. Also better special config recognition (like gui-types for MultiTypeGui etc.)
        if param["annotation"] is inspect.Parameter.empty:
            logging.warning(f"No type annotation for parameter '{name}'. Skipping.")
            return None
        elif (
            type(param["annotation"]) is UnionType
        ):  # alias for typing.Union since Python 3.14
            args = get_args(param["annotation"])
            gui_type = next((arg for arg in args if arg is not NoneType), str)
            none_select = NoneType in args
        else:
            gui_type = param["annotation"]
            none_select = param["annotation"] == NoneType
        gui = default_type_guis.get(gui_type.__name__, MultiTypeGui)(
            data=self.config,
            name=name,
            default=param["default"],
            none_select=none_select,
            groupbox_layout=False,
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
    def __init__(
        self,
        code: str | PathLike | None = None,
        allow_exec: bool = False,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        # Attributes
        self.func_config = {}
        self.current_func = None
        self.editors = {}
        self.allow_exec = allow_exec
        self.fixed_categories = {}
        # UI
        layout = QHBoxLayout(self)
        self.setWindowTitle("Import Function")
        # Init code editor tabs
        tab_layout = QVBoxLayout()
        # Load button
        load_bt = QPushButton(qta.icon("fa6s.file-import"), "Load File")
        load_bt.clicked.connect(lambda x: self.load_file(None))
        tab_layout.addWidget(load_bt)
        # Tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.tabBarClicked.connect(self.update_config)
        self.tab_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        tab_layout.addWidget(self.tab_widget)
        layout.addLayout(tab_layout)
        # Reanalyze button
        analyze_bt = QPushButton(qta.icon("mdi6.reload"), "Re-analyze Code")
        analyze_bt.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        analyze_bt.clicked.connect(self.reanalyze)
        tab_layout.addWidget(analyze_bt)
        # Init configuration
        config_layout = QFormLayout()
        config_layout.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint
        )
        layout.addLayout(config_layout)
        # Add scope combobox
        self.scope_cmbx = QComboBox()
        self.scope_cmbx.addItems(["subject", "group", "custom"])
        config_layout.addRow("Scope", self.scope_cmbx)
        # Inputs Configuration
        self.inputs_layout = QFormLayout()
        self.inputs_layout.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint
        )
        config_layout.addRow("Inputs", self.inputs_layout)
        # Outputs Configuration
        self.outputs_layout = QFormLayout()
        self.outputs_layout.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint
        )
        config_layout.addRow("Outputs", self.outputs_layout)
        # Parameter configuration
        self.parameter_layout = QFormLayout()
        self.parameter_layout.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint
        )
        config_layout.addRow("Parameters", self.parameter_layout)

        # Analyze the code and populate the UI
        if code is not None:
            if isfile(code):
                self.load_file(code)
            else:
                self.analyze_code(code)
        self.open()

    def load_file(self, file_path: PathLike | str | None = None):
        self.clear_editor_tabs()
        if file_path is None:
            file_path = get_user_input(
                "Select File to load",
                "file",
                file_filter="Python Files (*.py)",
                parent=self,
            )
        if file_path is not None:
            with open(file_path) as f:
                code = f.read()
            self.analyze_code(code)

    def analyze_code(self, code):
        # Analyze the code to extract inputs and parameters
        namespace = {}
        if self.allow_exec:
            try:
                exec(code, globals=namespace)
            except Exception:
                exc_tuple = get_exception_tuple()
                ErrorDialog(exc_tuple, self, "There was an error executing the code.")
        tree = ast.parse(code)
        function_defs = [
            node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
        ]
        for func in function_defs:
            fixed = self.fixed_categories.get(
                func.name, {"inputs": [], "parameters": []}
            )
            if func.name not in self.func_config:
                self.func_config[func.name] = {"inputs": {}, "parameters": {}}
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
            default_args = func.args.defaults
            num_defaults = len(default_args)

            # Configure inputs
            input_config = self.func_config[func.name]["inputs"]
            inputs = [
                a.arg
                for a in args[: len(args) - num_defaults]
                if a.arg not in fixed["parameters"]
            ]
            # Add fixed inputs moved from parameters
            inputs += fixed["inputs"]
            # Add missing input-configurations
            for new_input in [ip for ip in inputs if ip not in input_config]:
                input_config[new_input] = {"accepted": [], "optional": False}
            # Remove old input-configurations
            for old_input in [ipc for ipc in input_config if ipc not in inputs]:
                logging.info(
                    f"Input '{old_input}' no longer present in function '{func.name}'. Removing from configuration."
                )
                del input_config[old_input]

            # Configure parameters
            param_config = self.func_config[func.name]["parameters"]
            parameters = [
                a.arg
                for a in args[len(args) - num_defaults :]
                if a.arg not in fixed["inputs"]
            ]
            # Add fixed parameters moved from inputs
            parameters += fixed["parameters"]
            # Remove old parameters if they are not longer present
            for old_param in [p for p in param_config if p not in parameters]:
                logging.info(
                    f"Parameter '{old_param}' no longer present in function '{func.name}'. Removing from configuration."
                )
                del param_config[old_param]

            # Get type-hints from function definition if exec is allowed
            type_hints = {}
            if func.name in namespace:
                type_hints.update(get_type_hints(namespace[func.name]))

            # Update parameter configuration
            for i, p in enumerate(parameters):
                if p not in param_config:
                    param_config[p] = {}
                gui_name = None
                # Type-hints from the function if exec allowed
                if p in type_hints:
                    type_hint = type_hints[p]
                    if (
                        isinstance(type_hint, UnionType)
                        or get_origin(type_hint) is Union
                    ):
                        gui_name = MultiTypeGui.__name__
                        types = get_args(type_hint)
                        if NoneType in types:
                            param_config[p]["none_select"] = True
                        param_config[p]["types"] = [
                            str(t) for t in types if t is not NoneType
                        ]
                    else:
                        gui_name = default_type_guis[type_hint.__name__].__name__
                try:
                    default = ast.literal_eval(default_args[i])
                except (TypeError, ValueError):
                    logging.warning(
                        f"Could not evaluate default value for parameter '{p}' in function '{func.name}'. It and the gui type need to be set manually."
                    )
                else:
                    if p not in type_hints:
                        gui_name = default_type_guis[type(default).__name__].__name__
                    param_config[p]["default"] = default
                param_config[p]["gui"] = gui_name

            # Extract outputs from return statement
            returns = [node for node in ast.walk(func) if isinstance(node, ast.Return)]
            if len(returns) == 0:
                logging.info(
                    f"No return statements found in function '{func.name}'. No outputs will be registered and this node will be a dead end."
                )
            elif len(returns) > 1:
                logging.warning(
                    f"Multiple return statements found in function '{func.name}'. Only the name of the first return value will be set as output. This may lead to unexpected behavior."
                )
            else:
                ret = returns[0]
                if isinstance(ret.value, ast.Tuple):
                    for val in ret.value.elts:
                        if not isinstance(val, ast.Name):
                            raise_user_attention(
                                f"Return value in function '{func.name}' is not a name. Only constant return values are supported currently.",
                                "warning",
                                self,
                            )
                            return
                    self.func_config[func.name]["outputs"] = [
                        e.id for e in ret.value.elts
                    ]
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

    def clear_editor_tabs(self):
        # Clear editor tabs
        for idx in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(idx)
            widget.deleteLater()
        self.tab_widget.clear()

    def reanalyze(self):
        # Get code from editors
        code = self.get_code()
        self.clear_editor_tabs()
        self.analyze_code(code)

    @staticmethod
    def _populate_config(config_items, layout, config_slot, move_slot):
        # Remove existing entries
        while layout.rowCount() > 0:
            layout.removeRow(0)
        # Add entries
        for item in config_items:
            bt_layout = QHBoxLayout()
            move_bt = QPushButton()
            move_bt.setSizePolicy(
                QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum
            )
            move_bt.setIcon(qta.icon("fa5s.exchange-alt"))
            move_bt.clicked.connect(partial(move_slot, item))
            bt_layout.addWidget(move_bt)
            ip_bt = QPushButton()
            ip_bt.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
            ip_bt.setIcon(qta.icon("fa5s.cog"))
            ip_bt.clicked.connect(partial(config_slot, item))
            bt_layout.addWidget(ip_bt)
            layout.addRow(item, bt_layout)

    def update_config(self, idx):
        self.current_func = list(self.func_config.keys())[idx]
        # Update inputs
        self._populate_config(
            self.func_config[self.current_func]["inputs"],
            self.inputs_layout,
            self.input_configuration,
            self.move_item,
        )
        # Update outputs
        # ToDo: Change appearance if config unnecessary
        self._populate_config(
            self.func_config[self.current_func]["outputs"],
            self.outputs_layout,
            self.output_configuration,
            self.move_item,
        )
        # Update parameters
        self._populate_config(
            self.func_config[self.current_func]["parameters"],
            self.parameter_layout,
            self.param_configuration,
            self.move_item,
        )

    def get_code(self):
        code = ""
        for func_name, editor in self.editors.items():
            code += editor.toPlainText() + "\n\n"
            self.func_config[func_name]["code"] = editor.toPlainText()
        return code

    def move_item(self, item):
        """Move item between inputs and parameters."""
        if self.current_func not in self.fixed_categories:
            self.fixed_categories[self.current_func] = {"inputs": [], "parameters": []}
        if item in self.func_config[self.current_func]["inputs"]:
            # Remove from input configuration
            self.func_config[self.current_func]["inputs"].pop(item)
            # Add to parameter configuration
            self.func_config[self.current_func]["parameters"][item] = {}
            # Set to fixed container to avoid reset on reanalyze
            if item in self.fixed_categories[self.current_func]["inputs"]:
                # If changed before from (origin) parameters
                self.fixed_categories[self.current_func]["inputs"].remove(item)
            else:
                # If origin input and changed to parameters
                self.fixed_categories[self.current_func]["parameters"].append(item)
        elif item in self.func_config[self.current_func]["parameters"]:
            # Remove from configuration
            self.func_config[self.current_func]["parameters"].pop(item)
            # Add to input configuration
            self.func_config[self.current_func]["inputs"][item] = {
                "accepted": [],
                "optional": False,
            }
            if item in self.fixed_categories[self.current_func]["parameters"]:
                # If changed before from (origin) inputs
                self.fixed_categories[self.current_func]["parameters"].remove(item)
            else:
                # If origin parameter and changed to inputs
                self.fixed_categories[self.current_func]["inputs"].append(item)
        self.update_config(self.tab_widget.currentIndex())

    def input_configuration(self, input_name):
        config = self.func_config[self.current_func]["inputs"][input_name]
        InputConfiguration(input_name, config, parent=self)

    def output_configuration(self, output_name):
        # ToDo: Remove if unnecessary
        pass

    def param_configuration(self, param_name):
        # Passing the configuration dict works since ParameterWidgets will fill
        # the existing container.
        config = self.func_config[self.current_func]["parameters"][param_name]
        ParameterConfiguration(param_name, config, parent=self)

    def closeEvent(self, event):
        # Update the code in the configuration before closing
        for func_name, editor in self.editors.items():
            self.func_config[func_name]["code"] = editor.toPlainText()
        # Check for mandatory configuration items
        warning_msg = "The following mandatory configuration items are missing:\n"
        ok = True
        for func_name, func_config in self.func_config.items():
            # Check function
            if len(func_config.get("inputs", [])) == 0:
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
            else:
                event.ignore()
