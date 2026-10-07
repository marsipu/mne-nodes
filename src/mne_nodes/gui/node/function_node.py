"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

from copy import deepcopy

from qtpy.QtWidgets import QGroupBox, QScrollArea, QVBoxLayout, QWidget

from mne_nodes.gui.code_editor import CodeEditorWidget
from mne_nodes.gui.node.base_node import BaseNode
from mne_nodes.gui.user_interaction import raise_user_attention
from mne_nodes.gui.widgets.misc_widgets import SimpleDialog


class FunctionNode(BaseNode):
    """Node for functions with inputs, outputs and parameters."""

    def __init__(self, ct, **kwargs):
        from mne_nodes.gui import parameter

        func_meta = ct.get_function_meta(kwargs["name"])
        if any(bool(v.get("write")) for v in func_meta["outputs"].values()):
            checkbox = "Save"
        else:
            checkbox = None
        super().__init__(ct, checkbox=checkbox, startable=True, **kwargs)
        # Set Tooltip
        self.setToolTip(func_meta.get("description", ""))
        # Initialize inputs and outputs
        for input_name, input_kwargs in func_meta["inputs"].items():
            accepted_ports = [input_name, *input_kwargs.get("accepted_ports", [])]
            if input_name == "raw":
                accepted_ports += [*ct.raw_types]
            optional = input_kwargs.get("optional", False)
            # Don't warn for existing ports since ports might be supplied via **kwargs
            self.add_input(
                input_name,
                multi_connection=True,
                accepted_ports=accepted_ports,
                optional=optional,
                warn_existing=False,
            )
        for output_name, output_kwargs in func_meta["outputs"].items():
            accepted_ports = [output_name, *output_kwargs.get("accepted_ports", [])]
            if output_name == "raw":
                accepted_ports += [*ct.raw_types]
            optional = output_kwargs.get("optional", False)
            self.add_output(
                output_name,
                multi_connection=True,
                accepted_ports=accepted_ports,
                optional=optional,
                warn_existing=False,
            )
        # Initialize the parameters
        self.parameter_guis = {}
        self.param_box = QGroupBox("Parameters")
        if len(func_meta["parameters"]) > 5:
            box_layout = QVBoxLayout(self.param_box)
            scroll_area = QScrollArea()
            scroll_area.setWidgetResizable(True)
            box_layout.addWidget(scroll_area)
            scroll_widget = QWidget()
            scroll_area.setWidget(scroll_widget)
            layout = QVBoxLayout(scroll_widget)
        else:
            layout = QVBoxLayout(self.param_box)
        for param_name, param_kwargs in func_meta["parameters"].items():
            param_kwargs = deepcopy(param_kwargs)
            param_kwargs["groupbox_layout"] = False
            gui_name = param_kwargs.pop("gui")
            gui = getattr(parameter, gui_name)
            # Importantly use self.name here to include the index suffix
            parameter_gui = gui(
                data=self.ct, name=param_name, function_name=self.name, **param_kwargs
            )
            layout.addWidget(parameter_gui)
            self.parameter_guis[param_name] = parameter_gui
        self.add_widget(self.param_box)

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)
        _func_code, start, end = self.ct.get_function_code(self.name)
        # ToDo: fix code editing
        plugin_config = self.ct.settings.get("plugin_config", {})
        plugin_name = self.ct.get_plugin_from_function(self.name)
        if plugin_name in plugin_config:
            file_path = plugin_config[plugin_name]["path"]
            editor_widget = CodeEditorWidget(
                file_section=(start, end), file_path=file_path
            )
            editor_widget.editor.codeSaved.connect(self.ct.reload_modules)
            self._editor_dialog = SimpleDialog(editor_widget)
            self._editor_dialog.open()
        else:
            raise_user_attention(
                "Source code not available for this function.",
                message_type="info",
                parent=self,
            )
