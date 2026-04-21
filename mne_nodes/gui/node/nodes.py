"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

from copy import deepcopy

import mne_bids
from mne_bids import get_datatypes
from mne_nodes import main_widget
from mne_nodes.gui import parameter_widgets
from mne_nodes.gui.base_widgets import CheckListProgress, ShallowTreeWidget
from mne_nodes.gui.base_widgets import SimpleDialog
from mne_nodes.gui.code_editor import CodeEditorWidget
from mne_nodes.gui.gui_utils import get_user_input
from mne_nodes.gui.node.base_node import BaseNode
from qtpy.QtWidgets import QScrollArea, QGroupBox, QPushButton
from qtpy.QtWidgets import QWidget, QComboBox, QVBoxLayout


class InputWidget(QWidget):
    def __init__(self, ct, **kwargs):
        super().__init__(**kwargs)
        self.ct = ct
        self.list_widget = None
        self.setLayout(QVBoxLayout())

        # Initialize Widgets
        self.root_bt = QPushButton("Set BIDS Root Directory")
        self.root_bt.clicked.connect(self.set_root)
        self.group_cmbx = QComboBox()
        self.group_cmbx.addItems(
            ["files", "subject", "session", "run", "task", "custom"]
        )
        self.group_cmbx.currentTextChanged.connect(self.cmbx_changed)
        self.layout().addWidget(self.group_cmbx)

    def set_root(self):
        new_root = get_user_input(
            "Select BIDS root directory", "folder", cancel_allowed=True
        )
        if new_root is not None:
            self.ct.bids_root = new_root

    def cmbx_changed(self, group_by):
        # Remove old widget
        if self.list_widget is not None:
            self.layout().removeWidget(self.list_widget)
            self.list_widget.deleteLater()
        data = mne_bids.get_entity_vals(self.ct.bids_root, group_by)
        if group_by not in self.ct.selected_inputs:
            self.ct.selected_inputs[group_by] = []
        if group_by == "custom":
            data = self.ct.get("custom_groups")
            self.list_widget = ShallowTreeWidget(
                data,
                checked=self.ct.selected_inputs[group_by],
                headers=["Group Name", "Subjects"],
            )
        else:
            self.list_widget = CheckListProgress(
                data, checked=self.ct.selected_inputs[group_by]
            )
        # Always save to the config the latest input selection
        self.list_widget.checkedChanged.connect(self.save_input_selection)
        self.layout().addWidget(self.list_widget)

    def save_input_selection(self):
        self.ct.set("selected_inputs", self.ct.selected_inputs)


class InputNode(BaseNode):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Set name to dataset name if available
        dataset_name = self.ct.get_dataset_name()
        if dataset_name is not None:
            self.name = dataset_name

        # Add input widget
        self.input_widget = InputWidget(self.ct)
        self.add_widget(self.input_widget)

        # Add data-types as outputs
        data_types = get_datatypes(self.ct.bids_root)
        for dt in data_types:
            self.add_output(dt, multi_connection=True)


class FunctionNode(BaseNode):
    """Node for functions with inputs, outputs and parameters."""

    def __init__(self, ct, **kwargs):
        super().__init__(ct, checkable=True, **kwargs)
        func_meta = ct.get_function_meta(self.name)
        # Initialize inputs and outputs
        for input_name in func_meta["inputs"]:
            self.add_input(
                input_name, multi_connection=True, accepted_ports=[input_name]
            )
        for output_name in func_meta["outputs"]:
            self.add_output(
                output_name, multi_connection=True, accepted_ports=[output_name]
            )
        # Initialize the parameters
        self.parameter_guis = {}
        widget = QGroupBox("Parameters")
        if len(func_meta["parameters"]) > 5:
            box_layout = QVBoxLayout(widget)
            scroll_area = QScrollArea()
            scroll_area.setWidgetResizable(True)
            box_layout.addWidget(scroll_area)
            scroll_widget = QWidget()
            scroll_area.setWidget(scroll_widget)
            layout = QVBoxLayout(scroll_widget)
        else:
            layout = QVBoxLayout(widget)
        for param_name, param_kwargs in func_meta["parameters"].items():
            param_kwargs = deepcopy(param_kwargs)
            param_kwargs["groupbox_layout"] = False
            gui_name = param_kwargs.pop("gui")
            gui = getattr(parameter_widgets, gui_name)
            # Importantly use self.name here to include the index suffix
            parameter_gui = gui(
                data=self.ct, name=param_name, function_name=self.name, **param_kwargs
            )
            layout.addWidget(parameter_gui)
            self.parameter_guis[param_name] = parameter_gui
        self.add_widget(widget)

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)
        func_code, start, end = self.ct.get_function_code(self.name)
        func_meta = self.ct.get_function_meta(self.name)
        file_path = self.ct.module_meta[func_meta["module"]]["module"]
        editor_widget = CodeEditorWidget(
            main_widget(), file_section=(start, end), file_path=file_path
        )
        editor_widget.editor.codeSaved.connect(self.ct.reload_modules)
        SimpleDialog(editor_widget)
        # ToDo: Get function


class AssignmentNode(BaseNode):
    """This node assigns the input from 1 to an input upstream from 2, which
    then leads to runningo the functions before for input 2 while caching input
    1."""

    # ToDo:
    # Checks for assignments and if there are pairs for each input.
    # Checks also for inputs in multiple pairs.
    # Status color and status message (like "24/28 assigned")
    # Should change port names depending on data-type connected
    def __init__(self, ct, **kwargs):  # **kwargs just for demo, later not needed
        super().__init__(ct, **kwargs)
        self.name = "Assignment Node"


class InteractionNode(BaseNode):
    """This node provides a way to directly interact with the data."""

    # ToDo:
    # - Create a Console-like editor with inputs from input-node
    def __init__(self, ct, **kwargs):
        super().__init__(ct, **kwargs)
        self.name = "Interaction Node"


class ExportNode(BaseNode):
    """This node provides a way to export the data."""

    # ToDo:
    # - Create a way to export the data to a file or a database
    def __init__(self, ct, **kwargs):
        super().__init__(ct, **kwargs)
        self.name = "Export Node"
