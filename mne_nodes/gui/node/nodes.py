# -*- coding: utf-8 -*-
import logging

from qtpy.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QPushButton,
    QDialog,
    QScrollArea,
    QGroupBox,
)

from mne_nodes.gui import parameter_widgets
from mne_nodes.gui.base_widgets import CheckList
from mne_nodes.pipeline.exception_handling import get_exception_tuple
from mne_nodes.gui.loading_widgets import AddFilesWidget, AddMRIWidget
from mne_nodes.gui.node.base_node import BaseNode


class InputNode(BaseNode):
    """Node for input data-types."""

    def __init__(self, ct, data_type="raw", name="All", **kwargs):
        # Check if data_type is valid
        if data_type not in ct.input_data_types:
            raise ValueError(
                f"Invalid data_type '{data_type}'. "
                f"Valid types are: {','.join(ct.input_data_types.keys())}"
            )
        self.data_type = data_type
        name = f"{ct.input_data_types[data_type]} | {name}"
        super().__init__(ct, name=name, **kwargs)

        # Add the output port
        self.add_output(self.data_type, multi_connection=True)

        # Initialize the main widget with the input list
        self.main_widget = QWidget()
        layout = QVBoxLayout(self.main_widget)
        import_bt = QPushButton("Import")
        import_bt.clicked.connect(self.add_files)
        layout.addWidget(import_bt)
        input_list = CheckList(
            ct.inputs[data_type],
            ct.selected_inputs,
            ui_button_pos="bottom",
            show_index=True,
            title=f"Select {data_type}",
        )
        layout.addWidget(input_list)
        self.add_widget(self.main_widget)

    def add_files(self):
        # This decides, wether the dialog is rendered outside or inside the scene
        dlg = QDialog(self.viewer)
        dlg.setWindowTitle("Import Files")
        if self.data_type == "MEEG":
            widget = AddFilesWidget(self.ct)
        else:
            widget = AddMRIWidget(self.ct)
        dlg_layout = QVBoxLayout(dlg)
        dlg_layout.addWidget(widget)
        dlg.open()


class FunctionNode(BaseNode):
    """Node for functions with inputs, outputs and parameters."""

    def __init__(self, ct, function, **kwargs):
        super().__init__(ct, **kwargs)
        self.function = function
        self.name = function
        self.func_meta = ct.function_metas.get(function, None)
        if self.func_meta is None:
            raise RuntimeError(
                f"Function metadata for '{function}' not found in controller."
            )

        # Initialize inputs and outputs
        for input_name in self.func_meta["inputs"]:
            self.add_input(
                input_name, multi_connection=True, accepted_ports=[input_name]
            )
        for output_name in self.func_meta["outputs"]:
            self.add_output(
                output_name, multi_connection=True, accepted_ports=[output_name]
            )

        widget = QGroupBox("Parameters")
        layout = QVBoxLayout(widget)
        if len(self.parameters) > 5:
            widget = QScrollArea()
            sub_widget = QWidget()
            layout = QVBoxLayout(sub_widget)
            widget.setWidget(sub_widget)

        for param_name in self.func_meta["parameters"]:
            param_kwargs = self.ct.parameter_metas.get(param_name, None)
            if param_kwargs is None:
                raise RuntimeError(
                    f"Parameter metadata for '{param_name}' not found in controller."
                )
            gui_name = param_kwargs.pop("gui", None)
            if gui_name is None:
                raise RuntimeError(
                    f"Parameter '{param_name}' does not have a GUI defined in metadata."
                )
            gui = getattr(parameter_widgets, gui_name, None)
            if gui is None:
                raise RuntimeError(
                    f"GUI widget '{gui_name}' for parameter '{param_name}' not found."
                )
            try:
                parameter_gui = gui(data=self.ct, **param_kwargs)
            except Exception:
                err_tuple = get_exception_tuple()
                logging.error(
                    f"Initialization of Parameter-Widget for '{param_name}' "
                    f"with {param_kwargs} failed:\n"
                    f"{err_tuple[1]}"
                )
            else:
                layout.addWidget(parameter_gui)
        self.add_widget(widget)

    def to_dict(self):
        """Override dictionary representation because of additional attributes."""
        node_dict = super().to_dict()
        node_dict["function"] = self.function

        return node_dict

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)
        # Get function
        # func_code, start, end = self.ct.get_function_code(self.function)
        # dlg = QDialog(self.viewer)


class AssignmentNode(BaseNode):
    """This node assigns the input from 1 to an input upstream from 2, which then leads
    to runningo the functions before for input 2 while caching input 1."""

    # ToDo:
    # Checks for assignments and if there are pairs for each input.
    # Checks also for inputs in multiple pairs.
    # Status color and status message (like "24/28 assigned")
    # Should change port names depending on data-type connected
    def __init__(self, ct, **kwargs):  # **kwargs just for demo, later not needed
        super().__init__(ct, **kwargs)
        self.name = "Assignment Node"
