"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

from copy import deepcopy

from qtpy.QtCore import QRectF
from qtpy.QtGui import QColor, QPainter, QPen
from qtpy.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QPushButton,
    QStyle,
    QStyleOptionTabWidgetFrame,
    QTabBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from mne_nodes.gui.colors import (
    ACCENT_OPACITY,
    ACTIVE_ACCENT_OPACITY,
    CATEGORY_DATATYPES,
    datatype_color,
)
from mne_nodes.gui.data_overview import DataOverviewDialog
from mne_nodes.gui.node.base_node import BaseNode
from mne_nodes.gui.user_interaction import get_user_input
from mne_nodes.gui.widgets.list_widgets import CheckListProgress
from mne_nodes.gui.widgets.tree_widgets import CustomGroupTreeWidget, ShallowTreeWidget


class DatatypeTabBar(QTabBar):
    """Native-looking tabs with restrained datatype-color underline accents."""

    def paintEvent(self, event) -> None:
        """Keep native tab styling and overlay only a thin semantic accent."""
        super().paintEvent(event)
        painter = QPainter(self)
        for index in range(self.count()):
            datatype = self.tabData(index)
            color = datatype_color(datatype) if isinstance(datatype, str) else None
            if color is None:
                continue
            accent = QColor(color)
            opacity = (
                ACTIVE_ACCENT_OPACITY
                if index == self.currentIndex() and self.isTabEnabled(index)
                else ACCENT_OPACITY
            )
            accent.setAlphaF(opacity)
            rect = self.tabRect(index).adjusted(8, 0, -8, -3)
            rect.setTop(rect.bottom() - 1)
            painter.fillRect(rect, accent)
        painter.end()


class DatatypeTabWidget(QTabWidget):
    """Datatype tabs with a subtle matching border around the active page."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setTabBar(DatatypeTabBar(self))
        self.currentChanged.connect(self.update)

    def paintEvent(self, event) -> None:
        """Tint only the native page frame, leaving page contents unchanged."""
        super().paintEvent(event)
        datatype = self.tabBar().tabData(self.currentIndex())
        color = datatype_color(datatype) if isinstance(datatype, str) else None
        if color is None:
            return
        option = QStyleOptionTabWidgetFrame()
        self.initStyleOption(option)
        frame = self.style().subElementRect(
            QStyle.SubElement.SE_TabWidgetTabPane, option, self
        )
        accent = QColor(color)
        accent.setAlphaF(ACCENT_OPACITY)
        painter = QPainter(self)
        painter.setPen(QPen(accent, 1))
        painter.drawRect(QRectF(frame).adjusted(0.5, 0.5, -0.5, -0.5))
        painter.end()


class InputWidget(QWidget):
    def __init__(self, ct, **kwargs):
        super().__init__(**kwargs)
        self.ct = ct
        self.selected_inputs = self.ct.get("selected_inputs")
        layout = QVBoxLayout()
        self.setLayout(layout)
        self.setMinimumSize(400, 300)

        # Add bids-root button
        hbox = QHBoxLayout()
        layout.addLayout(hbox)
        self.root_bt = QPushButton("Set BIDS Root")
        self.root_bt.clicked.connect(self.set_root)
        hbox.addWidget(self.root_bt)
        self.overview_bt = QPushButton("Data overview")
        self.overview_bt.clicked.connect(self.show_data_overview)
        hbox.addWidget(self.overview_bt)

        # Datatype Tab Widget
        self.tab_widget = DatatypeTabWidget()
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
        self.ct.discard_legacy_segmentation_checks()
        self.selected_inputs = self.ct.get("selected_inputs")
        # Clear tab widget
        self.tab_widget.clear()
        # Populate lists
        for dt, data in self.ct.get_all_datatype_items().items():
            checked = self.selected_inputs.setdefault(dt, [])
            dt_list = CheckListProgress(data, checked=checked, ui_button_pos="bottom")
            dt_list.checkedChanged.connect(
                lambda slct, dt=dt: self.ct.input_selection_changed(slct, data_type=dt)
            )
            index = self.tab_widget.addTab(dt_list, dt)
            self.tab_widget.tabBar().setTabData(index, dt)
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
                self.ct.get_all_datatype_items(),
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
        self.group_tree.dataChanged.connect(self.ct.refresh_input_outputs)
        self.group_tree.checkedChanged.connect(
            lambda checked, group_by=group_by: self.ct.input_selection_changed(
                checked, data_type=group_by
            )
        )
        self.group_layout.addWidget(self.group_tree)
        self.group_widget.update()

    def show_data_overview(self) -> None:
        """Show availability in a native dialog outside the node's graphics proxy."""
        dialog = DataOverviewDialog(self.ct, self.ct.viewer)
        dialog.open()
        dialog.update_widgets()


class InputNode(BaseNode):
    def __init__(self, **kwargs):
        super().__init__(startable=True, deletable=False, **kwargs)
        self.input_widget = None
        self._empty_rooms: list[str] | None = None
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

        # Add data-types as outputs
        data_types = self.ct.get_datatypes()
        for port in list(self.outputs):
            if port.name not in data_types:
                self.remove_port(port)
        for dt in data_types:
            port_kwargs = existing_outputs.get(dt, {})
            accepted = port_kwargs.get("accepted_ports") or [dt]
            if dt in self.ct.raw_types + ["raw_er"] and "raw" not in accepted:
                accepted.append("raw")
            if dt not in accepted:
                accepted.append(dt)
            existing = next((p for p in self.outputs if p.name == dt), None)
            if existing is not None:
                existing.accepted_ports = accepted
                existing.update_datatype_color()
                continue
            self.add_output(
                dt,
                multi_connection=port_kwargs.get("multi_connection", True),
                accepted_ports=accepted,
                old_id=port_kwargs.get("old_id"),
                warn_existing=False,
            )
        # Use the palette's category and datatype order; keep unknown types last.
        order = {
            datatype: index
            for index, datatype in enumerate(
                datatype
                for datatypes in CATEGORY_DATATYPES.values()
                for datatype in datatypes
            )
        }
        ordered = sorted(
            self.outputs,
            key=lambda port: (order.get(port.name.lower(), len(order)), port.name),
        )
        for port in ordered:
            self._outputs.move_to_end(port.id)
        self.update_output_availability()
        if self.scene() is not None:
            self.draw_node()

    def update_output_availability(self, *, selection_only: bool = False) -> None:
        """Disable unavailable outputs while retaining their existing connections."""
        empty_rooms = (
            self._empty_rooms
            if selection_only and self._empty_rooms is not None
            else self.ct.get_datatype_items("emptyroom")
        )
        self._empty_rooms = empty_rooms
        subjects = self.ct.get_datatype_items("subject")
        inventory = {port.name: [] for port in self.outputs}
        inventory.update(subject=subjects, raw_er=empty_rooms)
        unavailable = self.ct.input_output_availability(inventory=inventory)
        associated = {"subject": bool(subjects), "raw_er": bool(empty_rooms)}
        visibility_changed = False
        for port in self.outputs:
            reason = unavailable.get(port.name, "")
            if port.name in associated:
                visible = associated[port.name]
                visibility_changed |= port.isVisible() != visible
                port.setVisible(visible)
                if not visible:
                    reason = f"No {port.name} data in this dataset."
            port.setEnabled(not reason)
            port.setOpacity(0.35 if reason else 1.0)
            port.setToolTip(reason)
        if visibility_changed and self.scene() is not None:
            self.draw_node()
