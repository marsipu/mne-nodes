"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

from copy import deepcopy

from qtpy.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QPushButton,
    QScrollArea,
    QGroupBox,
    QHBoxLayout,
)

from mne_nodes import main_widget
from mne_nodes.gui import parameter_widgets
from mne_nodes.gui.base_widgets import CheckList, SimpleDialog
from mne_nodes.gui.code_editor import CodeEditorWidget
from mne_nodes.gui.loading_widgets import AddFilesWidget, AddMRIWidget
from mne_nodes.gui.node.base_node import BaseNode
from mne_nodes.pipeline.data_import import import_dataset


class InputNode(BaseNode):
    """Node for input data-types."""

    def __init__(self, ct, data_type="raw", name="All", **kwargs):
        super().__init__(ct, name=name, startable=True, **kwargs)
        # Check if data_type is valid
        if data_type not in ct.get("input_types"):
            raise ValueError(
                f"Invalid data_type '{data_type}'. "
                f"Valid types are: {','.join(ct.get('input_types').keys())}"
            )
        self.data_type = data_type

        # Add the output port (if not already initialized with kwargs)
        self.add_output(self.data_type, multi_connection=True)

        # Initialize the main widget with the input list
        self.main_widget = QWidget()
        layout = QVBoxLayout(self.main_widget)
        bt_layout = QHBoxLayout()
        import_bt = QPushButton("Import")
        import_bt.clicked.connect(self.add_files)
        bt_layout.addWidget(import_bt)
        sample_bt = QPushButton("Sample-Data")
        sample_bt.clicked.connect(self.load_sample)
        bt_layout.addWidget(sample_bt)
        layout.addLayout(bt_layout)
        input_list = CheckList(
            ct.get("inputs")[data_type][name],
            ct.get("selected_inputs"),
            ui_button_pos="bottom",
            show_index=True,
            title=f"Select {data_type}",
        )
        layout.addWidget(input_list)
        self.add_widget(self.main_widget)

    def add_files(self):
        if self.data_type == "raw":
            widget = AddFilesWidget(self.ct)
        else:
            widget = AddMRIWidget(self.ct)
        SimpleDialog(widget, title="Import Files")

    def to_dict(self):
        """Serialize the InputNode to a dictionary."""
        node_dict = super().to_dict()
        node_dict["data_type"] = self.data_type
        return node_dict

    def load_sample(self):
        import_dataset(self.ct, dataset="sample", group="All")
        # WorkerDialog(parent=main_widget(), function=import_dataset,
        #              controller=self.ct, dataset="sample",
        #              show_console=True, close_directly=False)


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
