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

from mne_nodes.logger import logger


class PluginManagerDlg(QDialog):
    """A dialog listing all registered plugins with per-plugin actions.

    Each plugin entry shows its name, type and status (enabled/disabled)
    alongside two action buttons:

    * **Disable / Enable** – toggles loading of the plugin on future
      sessions of this device without removing it from the project config.
        * **Remove** – unregisters the plugin from the project without deleting
            its files or uninstalling its distribution.

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
            if item.widget():
                item.widget().deleteLater()

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
        from mne_nodes.gui.gui_utils import ask_user

        question = (
            f"Remove plugin '{plugin_name}' from this project?\n"
            "The plugin files and installed package will not be changed."
        )
        if not ask_user(question):
            return
        self.ct.remove_plugin(plugin_name)
        self._refresh_rows()
