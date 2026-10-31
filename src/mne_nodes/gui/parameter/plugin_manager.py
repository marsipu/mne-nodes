from pathlib import Path

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from mne_nodes.backend.exception_handling import get_exception_tuple
from mne_nodes.backend.package_utils import install_local_plugin
from mne_nodes.backend.plugin_package import (
    copy_plugin_source,
    get_plugin_source,
    initialize_plugin_repository,
)
from mne_nodes.gui.dialogs import ErrorDialog
from mne_nodes.gui.function_widgets import FunctionImporter
from mne_nodes.gui.plugin_package import request_package_metadata
from mne_nodes.gui.user_interaction import ask_user, get_user_input
from mne_nodes.logger import logger

_STATUS_COLORS = {
    "enabled": "#16a34a",
    "disabled": "#64748b",
    "not loaded": "#d97706",
    "error": "#dc2626",
}


def _rgb(color: str) -> str:
    """Convert ``#rrggbb`` to a comma-separated RGB string for stylesheets."""
    return ", ".join(str(int(color[i : i + 2], 16)) for i in (1, 3, 5))


class PluginManagerDlg(QDialog):
    """Manage registered and discoverable installed plugins in one dialog.

    Each plugin entry shows its name, type and status (enabled/disabled)
    alongside action buttons:

    * **Disable / Enable** – toggles loading of the plugin on future
      sessions of this device without removing it from the project config.
    * **Remove** – unregisters the plugin from the project without deleting
        its files or uninstalling its distribution.
    * **Edit** opens local source and configuration; installed distributions
      must first be copied to a local project.

    Parameters
    ----------
    parent_widget : QWidget
        Parent widget.
    controller : Controller
        The application controller.
    """

    def __init__(self, parent_widget, controller):
        super().__init__(parent_widget)
        self.ct = controller
        self.setWindowTitle("Manage Plugins")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(760, 560)
        self._build_ui()
        self.open()

    def _build_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setSpacing(10)
        header = QHBoxLayout()
        description = QLabel(
            "Installed plugins are discovered and enabled automatically. "
            "Plugins you disable stay disabled."
        )
        description.setWordWrap(True)
        header.addWidget(description, stretch=1)
        refresh_bt = QPushButton("Refresh")
        refresh_bt.setToolTip("Search the Python environment for new plugins.")
        refresh_bt.clicked.connect(self._discover_plugins)
        header.addWidget(refresh_bt)
        outer_layout.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        self._rows_layout = QVBoxLayout(container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(8)
        self._rows_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(container)
        outer_layout.addWidget(scroll)

        self._discover_plugins()

        footer = QHBoxLayout()
        footer.addStretch()
        close_bt = QPushButton("Close")
        close_bt.clicked.connect(self.close)
        footer.addWidget(close_bt)
        outer_layout.addLayout(footer)

    def _refresh_rows(self):
        """Clear and rebuild the plugin rows from the current controller state."""
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.hide()
                widget.deleteLater()

        plugin_meta = self.ct.get("plugin_meta", {})
        disabled_plugins = set(self.ct.settings.get("disabled_plugins", []))

        if not plugin_meta and not self.ct.installed_plugins:
            self._rows_layout.addWidget(QLabel("No plugins found."))

        for plugin_name, meta in plugin_meta.items():
            self._rows_layout.addWidget(
                self._make_row(plugin_name, meta, plugin_name in disabled_plugins)
            )
        for record in self.ct.installed_plugins.values():
            if "error" in record and record.get("plugin_name") not in plugin_meta:
                card, _actions = self._card(
                    record["entry_point_name"],
                    "error",
                    "Nodes unavailable",
                    f"Installed package: {record['distribution_name']} "
                    f"{record.get('version', '')}".strip(),
                    [record["error"]],
                )
                self._rows_layout.addWidget(card)

    def _discover_plugins(self) -> None:
        try:
            self.ct.discover_installed_plugins()
        except Exception:  # noqa: BLE001
            ErrorDialog(
                get_exception_tuple(), self, "Could not discover installed plugins."
            ).open()
        self._refresh_rows()

    @staticmethod
    def _pill(text: str, color: str, name: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName(name)
        # A translucent tint keeps the pill readable on light and dark themes.
        label.setStyleSheet(
            f"QLabel#{name} {{ color: {color}; "
            f"background-color: rgba({_rgb(color)}, 38); "
            f"border: 1px solid rgba({_rgb(color)}, 110); border-radius: 9px; "
            "padding: 1px 9px; font-weight: 600; }"
        )
        return label

    def _card(
        self, title: str, status: str, node_text: str, details: str, errors: list[str]
    ) -> tuple[QFrame, QHBoxLayout]:
        color = _STATUS_COLORS[status]
        card = QFrame()
        card.setObjectName("plugin_card")
        card.setProperty("plugin_name", title)
        card.setStyleSheet(
            "QFrame#plugin_card { border: 1px solid palette(mid); "
            f"border-left: 4px solid {color}; border-radius: 6px; }}"
        )
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        header = QHBoxLayout()
        name = QLabel(title)
        name.setObjectName("plugin_title")
        name.setStyleSheet("font-size: 11pt; font-weight: 600;")
        header.addWidget(name)
        header.addWidget(self._pill(status, color, "plugin_status"))
        header.addStretch()
        count = QLabel(node_text)
        count.setObjectName("plugin_node_count")
        count.setStyleSheet("color: palette(placeholder-text);")
        header.addWidget(count)
        layout.addLayout(header)

        info = QLabel(details)
        info.setWordWrap(True)
        info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        info.setStyleSheet("color: palette(placeholder-text);")
        layout.addWidget(info)
        for error in errors:
            error_label = QLabel(error)
            error_label.setWordWrap(True)
            error_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            error_label.setStyleSheet(f"color: {color};")
            layout.addWidget(error_label)

        actions = QHBoxLayout()
        actions.addStretch()
        layout.addLayout(actions)
        return card, actions

    def _make_row(self, plugin_name: str, meta: dict, is_disabled: bool) -> QFrame:
        plugin_type = meta.get("plugin_type", "unknown")
        loaded = plugin_name in self.ct.plugins
        status = "disabled" if is_disabled else "enabled" if loaded else "not loaded"

        registrations = [
            record
            for record in self.ct.installed_plugins.values()
            if record.get("plugin_name") == plugin_name
        ]
        errors = [record["error"] for record in registrations if "error" in record]
        if errors and not is_disabled and not loaded:
            status = "error"
        installed = bool(registrations)
        if installed:
            details = " · ".join(
                f"{record['distribution_name']} {record['version']}"
                for record in registrations
            )
        else:
            config_path = meta.get("config_path")
            source = Path(config_path).name if config_path else meta.get("module_name")
            details = f"{plugin_type.capitalize()} plugin"
            if source:
                details += f" · {source}"
        tooltip = None
        try:
            node_count = self.ct.plugin_node_count(plugin_name)
            node_text = f"Nodes: {node_count}"
        except (OSError, ValueError, TypeError, KeyError) as error:
            logger.warning("Cannot count nodes for %s: %s", plugin_name, error)
            node_text = "Nodes: unavailable"
            tooltip = str(error)
        card, actions = self._card(
            plugin_name, status, node_text, details, errors if not loaded else []
        )
        if tooltip:
            card.findChild(QLabel, "plugin_node_count").setToolTip(tooltip)
        if meta.get("config_path"):
            card.setToolTip(str(meta["config_path"]))

        edit_bt = QPushButton("Edit...", card)
        edit_bt.clicked.connect(lambda _checked, pn=plugin_name: self._edit_plugin(pn))
        actions.addWidget(edit_bt)

        toggle_label = "Enable" if is_disabled or not loaded else "Disable"
        toggle_bt = QPushButton(toggle_label, card)
        toggle_bt.clicked.connect(
            lambda _checked, pn=plugin_name, dis=is_disabled or not loaded: (
                self._toggle_plugin(pn, dis)
            )
        )
        actions.addWidget(toggle_bt)

        remove_bt = QPushButton("Remove", card)
        remove_bt.setEnabled(not installed)
        if installed:
            remove_bt.setToolTip(
                "Installed plugins remain discoverable. Disable the plugin instead."
            )
        remove_bt.clicked.connect(
            lambda _checked, pn=plugin_name: self._remove_plugin(pn)
        )
        actions.addWidget(remove_bt)

        return card

    def _edit_plugin(self, plugin_name: str) -> None:
        editor = None
        try:
            meta = self.ct.get("plugin_meta")[plugin_name]
            override = self.ct.settings.get("plugin_config", {}).get(plugin_name)
            source = get_plugin_source(meta, override)
            copied = False
            metadata = None
            git_pending = False
            install_pending = False
            if source.installed:
                if not ask_user(
                    "This plugin is installed in the Python environment. "
                    "Create a local package copy to edit instead? "
                    "The installed files will not be modified.",
                    parent=self,
                ):
                    return
                metadata = request_package_metadata(source.script_path.stem, self)
                if metadata is None:
                    return
                destination = get_user_input(
                    "Choose a project root for the local plugin copy.",
                    input_type="folder",
                    parent=self,
                )
                if destination is None:
                    return
                project_root = Path(destination).resolve()
                source = copy_plugin_source(source, project_root, metadata)
                copied = True
                git_pending = metadata.initialize_git
                install_pending = metadata.install_package

            def saved(_config_path: Path) -> None:
                nonlocal git_pending, install_pending
                if metadata is not None and source.project_root is not None:
                    if git_pending:
                        initialize_plugin_repository(
                            source.project_root, metadata.initial_branch
                        )
                        git_pending = False
                    if install_pending:
                        install_local_plugin(
                            source.project_root,
                            editable=metadata.editable_install,
                            parent=self,
                        )
                        install_pending = False
                disabled = plugin_name in self.ct.settings.get("disabled_plugins", [])
                if copied:
                    if disabled:
                        self.ct.set_dict_value(
                            "plugin_meta",
                            plugin_name,
                            {
                                "plugin_type": "path",
                                "config_path": source.config_path,
                                "script_path": source.script_path,
                            },
                        )
                    else:
                        self.ct.load_plugin_path(source.config_path)
                    overrides = self.ct.settings.get("plugin_config", {})
                    overrides.pop(plugin_name, None)
                    self.ct.settings.set("plugin_config", overrides)
                elif not disabled:
                    self.ct.reload_plugins(plugin_name)
                self._refresh_rows()

            editor = FunctionImporter(
                parent=self, source=source, on_saved=saved, register_on_save=copied
            )
            editor.open()
        except Exception:  # noqa: BLE001
            if editor is not None:
                editor.deleteLater()
            ErrorDialog(
                get_exception_tuple(), self, "Could not edit the plugin."
            ).open()

    def _toggle_plugin(self, plugin_name: str, currently_disabled: bool):
        try:
            if currently_disabled:
                self.ct.enable_plugin(plugin_name)
                logger.info(f"Plugin '{plugin_name}' enabled.")
            else:
                self.ct.disable_plugin(plugin_name)
                logger.info(f"Plugin '{plugin_name}' disabled.")
        except Exception:  # noqa: BLE001
            ErrorDialog(
                get_exception_tuple(), self, "Could not change plugin status."
            ).open()
        self._refresh_rows()

    def _remove_plugin(self, plugin_name: str):
        question = (
            f"Remove plugin '{plugin_name}' from this project?\n"
            "The plugin files and installed package will not be changed."
        )
        if not ask_user(question):
            return
        self.ct.remove_plugin(plugin_name)
        self._refresh_rows()
