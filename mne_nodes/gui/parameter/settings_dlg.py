from __future__ import annotations

from qtpy.QtGui import QFontDatabase
from qtpy.QtWidgets import QDialog, QPushButton, QVBoxLayout

from mne_nodes import iswin
from mne_nodes.gui.gui_utils import set_app_font_size, set_app_theme

from .bool_gui import BoolGui
from .combo_gui import ComboGui
from .int_gui import IntGui
from .string_gui import StringGui


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
