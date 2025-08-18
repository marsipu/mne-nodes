"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import json
import logging
from ast import literal_eval
from copy import deepcopy
from os import mkdir
from os.path import isfile, isdir
from pathlib import Path
from types import NoneType
from typing import Any, Dict, List, Optional, Union

from mne_nodes import gui_mode
from mne_nodes.pipeline.io import type_json_hook, TypedJSONEncoder

# ToDo: Next separate settings and enable loading them into parameters (e.g. n_jobs), finally make the node-test run
# Default Settings/QSettings
default_device_settings = {
    "config_path": None,
    "log_file_path": None,
    "fs_path": None,
    "wls_mne_path": None,
    "use_qthread": 1,
    "save_ram": 1,
    "enable_cuda": 0,
    "screen_ratio": 0.8,
    "screen_name": None,
    "app_theme": "auto",
    "app_style": "fusion",
    "app_font_size": 10,
}


class Settings:
    """Unified settings handler that uses Qt's QSettings if available,
    otherwise falls back to a JSON file in the user's home directory. On
    initialization, checks for a Qt installation and sets the backend
    accordingly. Since QSettings does not preserve types, the type is stored
    with the setting in QSettings.

    Methods
    -------
    value(setting, defaultValue=None)
        Returns the value for a given setting, with type conversion
        and fallback to default values.
    setValue(setting, value)
        Sets the value for a given setting.
    sync()
        Synchronizes the settings with the backend.
    childKeys()
        Returns all existing setting keys.
    remove(setting)
        Removes a setting.

    Attributes
    ----------
    qsettings : QSettings or None
        Reference to QSettings if available.
    settings_path : str
        Path to the JSON file if Qt is not available.
    settings : dict
        Dictionary with current settings (only for JSON backend).

    The class is independent of PyQt/PySide.
    """

    def __init__(self) -> None:
        self.default_qsettings = default_device_settings.copy()
        self.supported_types = [
            int,
            float,
            str,
            bool,
            tuple,
            list,
            dict,
            NoneType,
            Path,
        ]
        if gui_mode:
            from qtpy.QtCore import QSettings  # noqa: F401

            self.qsettings = QSettings()
            self.settings_path = None
            self.settings = None
        else:
            self.qsettings = None
            self.settings_path = Path.home() / ".mne-nodes" / ".mne_nodes.json"
            self.settings = None

    def load_settings(self) -> None:
        """Load settings from the JSON file if Qt is not available."""
        if not hasattr(self, "settings"):
            self.settings = deepcopy(self.default_qsettings)
        if isfile(self.settings_path):
            with open(self.settings_path) as file:
                self.settings = json.load(file, object_hook=type_json_hook)
        else:
            self.settings = deepcopy(self.default_qsettings)

    def write_settings(self) -> None:
        """Write settings to the JSON file if Qt is not available."""
        if not isdir(self.settings_path.parent):
            mkdir(self.settings_path.parent)
        with open(self.settings_path, "w") as file:
            json.dump(self.settings, file, indent=4, cls=TypedJSONEncoder)

    def get_default(self, name: str) -> Any:
        if name in self.default_qsettings:
            return self.default_qsettings[name]
        logging.warning(f"Setting '{name}' not found in default settings.")
        return None

    def value(self, setting: str, defaultValue: Any = None) -> Any:
        if gui_mode:
            loaded_value = self.qsettings.value(
                setting,
                defaultValue=defaultValue or self.default_qsettings.get(setting),
            )
            # Check if the type is stored in QSettings
            type_key = f"type_{setting}_type"
            type_str = self.qsettings.value(type_key, None)
            if type_str is not None and type(loaded_value).__name__ != type_str:
                if type_str == "bool":
                    loaded_value = loaded_value == "true"
                elif type_str == "Path":
                    loaded_value = Path(loaded_value)
                else:
                    try:
                        loaded_value = literal_eval(loaded_value)
                    except (SyntaxError, ValueError):
                        return self.get_default(setting)
            return loaded_value
        else:
            self.load_settings()
            if setting in self.settings:
                return self.settings[setting]
            if defaultValue is None:
                return self.get_default(setting)
            else:
                return defaultValue

    def setValue(self, setting: str, value: Any) -> None:
        if not any(isinstance(value, t) for t in self.supported_types):
            raise TypeError(
                f"Unsupported type {type(value)} for setting '{setting}'. "
                f"Supported types are: {self.supported_types}"
            )
        if gui_mode:
            if isinstance(value, Path):
                value_type = "Path"
            else:
                value_type = type(value).__name__
            self.qsettings.setValue(setting, value)
            # Store the type of the value in the QSettings too
            self.qsettings.setValue(f"type_{setting}_type", value_type)
        else:
            # Always load the settings to allow synchronization across multiple instances
            self.load_settings()
            self.settings[setting] = value
            self.write_settings()

    def sync(self) -> None:
        if gui_mode:
            self.qsettings.sync()
        else:
            self.write_settings()
            self.load_settings()

    def childKeys(self) -> List[str]:
        if gui_mode:
            return self.qsettings.childKeys()
        else:
            self.load_settings()
            return self.settings.keys()

    def remove(self, setting: str) -> None:
        if gui_mode:
            self.qsettings.remove(setting)
        else:
            self.load_settings()
            self.settings.pop(setting, None)
            self.write_settings()
