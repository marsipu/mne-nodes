from pathlib import Path

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QDialog,
    QGroupBox,
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


class PluginManagerDlg(QDialog):
    """A dialog listing all registered plugins with per-plugin actions.

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
        self.setMinimumWidth(480)
        self._build_ui()
        self.open()

    def _build_ui(self):
        outer_layout = QVBoxLayout(self)

        # Scrollable area for the plugin rows
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        self._rows_layout = QVBoxLayout(container)
        self._rows_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(container)
        outer_layout.addWidget(scroll)

        self._refresh_rows()

        close_bt = QPushButton("Close")
        close_bt.clicked.connect(self.close)
        outer_layout.addWidget(close_bt)

    def _refresh_rows(self):
        """Clear and rebuild the plugin rows from the current controller state."""
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()

        plugin_meta = self.ct.get("plugin_meta", {})
        disabled_plugins = set(self.ct.settings.get("disabled_plugins", []))

        if not plugin_meta:
            self._rows_layout.addWidget(QLabel("No plugins loaded."))
            return

        for plugin_name, meta in plugin_meta.items():
            self._rows_layout.addWidget(
                self._make_row(plugin_name, meta, plugin_name in disabled_plugins)
            )

    def _make_row(self, plugin_name: str, meta: dict, is_disabled: bool) -> QGroupBox:
        plugin_type = meta.get("plugin_type", "unknown")
        status = "disabled" if is_disabled else "enabled"

        group = QGroupBox(plugin_name)
        group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        row_layout = QHBoxLayout(group)

        info = QLabel(f"Type: {plugin_type} | Status: {status}")
        info.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row_layout.addWidget(info)

        edit_bt = QPushButton("Edit...")
        edit_bt.clicked.connect(lambda _checked, pn=plugin_name: self._edit_plugin(pn))
        row_layout.addWidget(edit_bt)

        toggle_label = "Enable" if is_disabled else "Disable"
        toggle_bt = QPushButton(toggle_label)
        toggle_bt.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        toggle_bt.clicked.connect(
            lambda _checked, pn=plugin_name, dis=is_disabled: self._toggle_plugin(
                pn, dis
            )
        )
        row_layout.addWidget(toggle_bt)

        remove_bt = QPushButton("Remove")
        remove_bt.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        remove_bt.clicked.connect(
            lambda _checked, pn=plugin_name: self._remove_plugin(pn)
        )
        row_layout.addWidget(remove_bt)

        return group

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
        if currently_disabled:
            self.ct.enable_plugin(plugin_name)
            logger.info(
                f"Plugin '{plugin_name}' enabled. It will be loaded on the next session."
            )
        else:
            self.ct.disable_plugin(plugin_name)
            logger.info(
                f"Plugin '{plugin_name}' disabled."
                " It will be skipped on the next session."
            )
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
