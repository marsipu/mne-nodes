"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

from copy import deepcopy

from qtpy.QtWidgets import QFrame, QGroupBox, QScrollArea, QVBoxLayout, QWidget

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
        super().__init__(ct, checkbox=checkbox, startable=False, **kwargs)
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
        self.parameter_frames = {}
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
            parameter_frame = QFrame()
            parameter_layout = QVBoxLayout(parameter_frame)
            parameter_layout.setContentsMargins(2, 2, 2, 2)
            parameter_layout.setSpacing(0)
            parameter_layout.addWidget(parameter_gui)
            layout.addWidget(parameter_frame)
            self.parameter_guis[param_name] = parameter_gui
            self.parameter_frames[param_name] = parameter_frame
            parameter_gui.paramChanged.connect(
                lambda _value, name=param_name: self._parameter_changed(name)
            )
        self.add_widget(self.param_box)

    def _parameter_changed(self, parameter_name):
        """Mark this parameter and its dependent nodes for rerun."""
        self.set_parameter_dirty(parameter_name, True)
        if self.viewer is not None:
            self.viewer.mark_dirty(self)
        else:
            self.dirty = True

    def set_parameter_dirty(self, parameter_name, dirty):
        """Show whether a parameter has changed since its node last ran."""
        frame = self.parameter_frames.get(parameter_name)
        if frame is None:
            return
        frame.setObjectName("changedParameter" if dirty else "")
        frame.setStyleSheet(
            "QFrame#changedParameter { border: 2px solid #ff7828; }" if dirty else ""
        )

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


class CommandNode(FunctionNode):
    """Node whose configured parameters form an executable argument vector."""

    def mouseDoubleClickEvent(self, event):
        metadata = self.ct.get_function_meta(self.name)
        raise_user_attention(
            "This node runs a command, not a Python function:\n"
            + " ".join(metadata["command"])
            + "\nEdit command/command_args in the plugin JSON configuration.",
            message_type="info",
            parent=self,
        )
