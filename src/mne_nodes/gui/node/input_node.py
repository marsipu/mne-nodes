"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

from copy import deepcopy

from qtpy.QtWidgets import QComboBox, QPushButton, QTabWidget, QVBoxLayout, QWidget

from mne_nodes.gui.node.base_node import BaseNode
from mne_nodes.gui.user_interaction import get_user_input
from mne_nodes.gui.widgets.list_widgets import CheckListProgress
from mne_nodes.gui.widgets.tree_widgets import CustomGroupTreeWidget, ShallowTreeWidget


class InputWidget(QWidget):
    def __init__(self, ct, **kwargs):
        super().__init__(**kwargs)
        self.ct = ct
        self.selected_inputs = self.ct.get("selected_inputs")
        layout = QVBoxLayout()
        self.setLayout(layout)
        self.setMinimumSize(400, 300)

        # Add bids-root button
        self.root_bt = QPushButton("Set BIDS Root Directory")
        self.root_bt.clicked.connect(self.set_root)
        layout.addWidget(self.root_bt)
        # Datatype Tab Widget
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)
        # Group Widget
        self.group_widget = QWidget()
        self.group_tree = None
        self.group_layout = QVBoxLayout(self.group_widget)
        self.group_cmbx = QComboBox()
        self.group_cmbx.addItems(self.ct.scopes)
        self.group_cmbx.currentTextChanged.connect(self.cmbx_changed)
        self.group_layout.addWidget(self.group_cmbx)

        self.update_widgets()

    def update_widgets(self):
        self.selected_inputs = self.ct.get("selected_inputs")
        # Clear tab widget
        self.tab_widget.clear()
        # Populate lists
        for dt, data in self.ct.get_datatype_items().items():
            if dt not in self.selected_inputs:
                self.selected_inputs[dt] = []
            dt_list = CheckListProgress(
                data, checked=self.selected_inputs[dt], ui_button_pos="bottom"
            )
            dt_list.checkedChanged.connect(
                lambda slct, dt=dt: self.ct.input_selection_changed(slct, data_type=dt)
            )
            self.tab_widget.addTab(dt_list, dt)
        # Initialize group widget via combobox
        self.tab_widget.addTab(self.group_widget, "Groups")
        gb = self.ct.get("group_by")
        if self.group_cmbx.currentText() != gb:
            self.group_cmbx.setCurrentText(gb)
        else:
            self.cmbx_changed(gb)
        # Update enable/disable of start button
        self.ct.check_selection_enable()

    def set_root(self):
        new_root = get_user_input(
            "Select BIDS root directory", "folder", cancel_allowed=True
        )
        if new_root is not None:
            self.ct.bids_root = new_root
        # Update widgets
        self.update_widgets()

    def cmbx_changed(self, group_by):
        # Remove old widget
        if self.group_tree is not None:
            self.group_layout.removeWidget(self.group_tree)
            self.group_tree.deleteLater()
        if group_by == "custom":
            data = self.ct.get("custom_groups")
        else:
            data = self.ct.get_group_by_strings(group_by)
        selected_inputs = self.ct.get("selected_inputs")
        if group_by not in selected_inputs:
            selected_inputs[group_by] = []
            self.ct.set("selected_inputs", selected_inputs)
        if group_by == "custom":
            self.group_tree = CustomGroupTreeWidget(
                self.ct.get_datatype_items(),
                data=data,
                checked=selected_inputs[group_by],
                headers=["Group Name", "Subjects"],
                ui_buttons=True,
                ui_button_pos="right",
            )
        else:
            self.group_tree = ShallowTreeWidget(
                data,
                checked=selected_inputs[group_by],
                headers=["Group Name", "Subjects"],
                ui_buttons=False,
                ui_button_pos="right",
            )
        # Always save to the config the latest input selection
        self.group_tree.dataChanged.connect(self.ct.flush)
        self.group_tree.checkedChanged.connect(
            lambda checked, group_by=group_by: self.ct.input_selection_changed(
                checked, data_type=group_by
            )
        )
        self.group_layout.addWidget(self.group_tree)
        self.group_widget.update()


class InputNode(BaseNode):
    def __init__(self, **kwargs):
        super().__init__(startable=True, deletable=False, **kwargs)
        self.input_widget = None
        self.update_widgets()

    def update_widgets(self):
        existing_outputs = deepcopy(
            {
                port.name: {
                    "multi_connection": port.multi_connection,
                    "accepted_ports": port.accepted_ports,
                    "old_id": port.old_id,
                }
                for port in self.outputs
            }
        )

        # Set name to dataset name if available
        dataset_name = self.ct.get_dataset_name()
        if dataset_name is not None:
            self.name = dataset_name

        # Add input widget
        if self.input_widget is None:
            self.input_widget = InputWidget(self.ct)
            self.add_widget(self.input_widget)
        else:
            self.input_widget.update_widgets()

        # Clear existing ports
        self.clear_ports()
        # Add data-types as outputs
        data_types = self.ct.get_datatypes()
        for dt in data_types:
            port_names = [dt]

            for name in port_names:
                if name in self.outputs:
                    continue
                port_kwargs = existing_outputs.get(name, {})
                accepted = port_kwargs.get("accepted_ports") or [name]
                if dt in self.ct.raw_types and "raw" not in accepted:
                    accepted.append("raw")
                if name not in accepted:
                    accepted.append(name)
                self.add_output(
                    name,
                    multi_connection=port_kwargs.get("multi_connection", True),
                    accepted_ports=accepted,
                    old_id=port_kwargs.get("old_id"),
                    warn_existing=False,
                )
        # Add event-id as output
        if "event_id" not in self.outputs:
            self.add_output(
                "event_id",
                multi_connection=True,
                accepted_ports=["event_id"],
                warn_existing=False,
            )
