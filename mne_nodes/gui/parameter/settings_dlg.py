from __future__ import annotations

from qtpy.QtCore import Qt
from qtpy.QtGui import QFontDatabase
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

from mne_nodes import iswin
from mne_nodes.gui.gui_utils import set_app_font_size, set_app_theme
from mne_nodes.logger import logger

from .bool_gui import BoolGui
from .combo_gui import ComboGui
from .int_gui import IntGui
from .string_gui import StringGui


class PluginManagerDlg(QDialog):
    """A dialog listing all registered plugins with per-plugin actions.

    Each plugin entry shows its name, type and status (enabled/disabled)
    alongside two action buttons:

    * **Disable / Enable** – toggles loading of the plugin on future
      sessions of this device without removing it from the project config.
    * **Delete / Uninstall** – permanently removes the plugin.  For
      ``path``-type plugins the script and config files are deleted from
      disk; for ``github``/``module`` plugins the distribution is
      uninstalled via pip.

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

        delete_label = "Delete Files" if plugin_type == "path" else "Uninstall"
        delete_bt = QPushButton(delete_label)
        delete_bt.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        delete_bt.clicked.connect(
            lambda _checked, pn=plugin_name: self._remove_plugin(pn)
        )
        row_layout.addWidget(delete_bt)

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

        plugin_meta = self.ct.get("plugin_meta", {}).get(plugin_name, {})
        plugin_type = plugin_meta.get("plugin_type", "unknown")
        if plugin_type == "path":
            question = (
                f"Delete all files for plugin '{plugin_name}'?\n"
                "This will permanently delete the script and config files from disk."
            )
        else:
            question = (
                f"Uninstall plugin '{plugin_name}'?\n"
                "This will uninstall the Python package via pip."
            )
        if not ask_user(question):
            return
        self.ct.remove_plugin(plugin_name)
        self._refresh_rows()


class SettingsDlg(QDialog):
    def __init__(self, parent_widget, controller):
        super().__init__(parent_widget)
        self.ct = controller

        self.settings_items = {
            "app_theme": {
                "gui_type": "ComboGui",
                "source_type": "Device",
                "slot": set_app_theme,
                "gui_kwargs": {
                    "alias": "Application Theme",
                    "description": "Changes the application theme (Restart required).",
                    "options": ["auto", "light", "dark", "high_contrast"],
                    "raise_missing": False,
                },
            },
            "app_font": {
                "gui_type": "ComboGui",
                "source_type": "Device",
                "slot": set_app_font_size,
                "gui_kwargs": {
                    "alias": "Application Font",
                    "description": "Changes default application font (Restart required).",
                    "options": list(
                        QFontDatabase.families(QFontDatabase.WritingSystem.Latin)
                    ),
                    "raise_missing": False,
                },
            },
            "app_font_size": {
                "gui_type": "IntGui",
                "source_type": "Device",
                "slot": set_app_font_size,
                "gui_kwargs": {
                    "alias": "Font Size",
                    "description": "Changes default application font-size (Restart required).",
                    "min_val": 5,
                    "max_val": 20,
                },
            },
            "img_format": {
                "gui_type": "ComboGui",
                "source_type": "Controller",
                "gui_kwargs": {
                    "alias": "Image Format",
                    "description": "Choose the image format for plots.",
                    "options": [".png", ".jpg", ".tiff"],
                },
            },
            "dpi": {
                "gui_type": "IntGui",
                "source_type": "Controller",
                "gui_kwargs": {
                    "alias": "DPI",
                    "description": "Set dpi for saved plots.",
                    "min_val": 10,
                    "max_val": 5000,
                },
            },
            "enable_cuda": {
                "gui_type": "BoolGui",
                "source_type": "Device",
                "gui_kwargs": {
                    "alias": "Enable CUDA",
                    "description": "Enable for CUDA support (system has to be setup for cuda as in https://mne.tools/stable/install/advanced.html#gpu-acceleration-with-cuda)",
                    "return_integer": True,
                },
            },
            "save_ram": {
                "gui_type": "BoolGui",
                "source_type": "Device",
                "gui_kwargs": {
                    "alias": "Save RAM",
                    "description": "Set to True on low RAM-Machines to avoid the process to be killed by the OS due to low Memory (with leaving it off, the pipeline goes a bit faster, because the data can be saved in memory).",
                    "return_integer": True,
                },
            },
            "fs_path": {
                "gui_type": "StringGui",
                "source_type": "Device",
                "gui_kwargs": {
                    "alias": "FREESURFER_HOME-Path",
                    "description": "Set the Path to the 'freesurfer'-directory of your Freesurfer-Installation (for Windows to the LINUX-Path of the Freesurfer-Installation in Windows-Subsystem for Linux(WSL))",
                    "none_select": True,
                },
            },
            "mne_path": {
                "gui_type": "StringGui",
                "source_type": "Device",
                "gui_kwargs": {
                    "alias": "MNE-WSL-Path",
                    "description": "Set the LINUX-Path to the mne-environment (e.g ...anaconda3/envs/mne) in Windows-Subsystem for Linux(WSL))",
                    "none_select": True,
                },
            },
        }

        if not iswin:
            self.settings_items.pop("mne_path")

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        gui_map = {
            "ComboGui": ComboGui,
            "IntGui": IntGui,
            "BoolGui": BoolGui,
            "StringGui": StringGui,
        }

        for setting, details in self.settings_items.items():
            gui_handle = gui_map[details["gui_type"]]
            source_type = details["source_type"]
            gui_kwargs = details["gui_kwargs"]
            if source_type == "Device":
                gui_kwargs["data"] = self.ct.settings
                gui_kwargs["default"] = self.ct.settings.default(setting)
            else:
                gui_kwargs["data"] = self.ct
                gui_kwargs["default"] = self.ct.default(setting)
            gui_kwargs["name"] = setting
            gui = gui_handle(**gui_kwargs)
            if details.get("slot"):
                gui.paramChanged.connect(details["slot"])
            layout.addWidget(gui)
        close_bt = QPushButton("Close")
        close_bt.clicked.connect(self.close)
        layout.addWidget(close_bt)

        self.setLayout(layout)
