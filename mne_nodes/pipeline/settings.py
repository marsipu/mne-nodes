"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import json
import logging
from ast import literal_eval
from copy import deepcopy
from os.path import join, isfile
from pathlib import Path

from mne_nodes import gui_mode

# ToDo: Next separate settings and enable loading them into parameters (e.g. n_jobs), finally make the node-test run
# Default Settings/QSettings
default_device_settings = {
    "config_path": None,
    "log_file_path": None,
    "gui": 1,
    "n_jobs": -1,
    "n_parallel": 1,
    "use_qthread": 1,
    "save_ram": 1,
    "enable_cuda": 0,
    "fs_path": None,
    "mne_path": None,
}


class QS:
    """Unified settings handler that uses Qt's QSettings if available, otherwise falls
    back to a JSON file in the user's home directory. On initialization, checks for a Qt
    installation and sets the backend accordingly. Since QSettings does not preserve
    types, the type is stored with the setting in QSettings. Supported types are: int,
    float, str, bool.

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

    def __init__(self):
        super().__init__()

        self.default_qsettings = default_device_settings.copy()
        self.supported_types = [int, float, str, bool]
        if gui_mode:
            from qtpy.QtCore import QSettings  # noqa: F401

            self.qsettings = QSettings()
            self.settings_path = None
        else:
            self.qsettings = None
            self.settings_path = join(Path.home(), ".mne_nodes.json")

    def load_settings(self):
        """Load settings from the JSON file if Qt is not available."""
        if not hasattr(self, "settings"):
            self.settings = deepcopy(self.default_qsettings)
        if isfile(self.settings_path):
            with open(self.settings_path) as file:
                self.settings = json.load(file)
        else:
            self.settings = deepcopy(self.default_qsettings)

    def write_settings(self):
        """Write settings to the JSON file if Qt is not available."""
        with open(self.settings_path, "w") as file:
            json.dump(self.settings, file)

    def get_default(self, name):
        if name in self.default_qsettings:
            return self.default_qsettings[name]
        logging.warning(f"Setting '{name}' not found in default settings.")
        return None

    def value(self, setting, defaultValue=None):
        if gui_mode:
            loaded_value = self.qsettings.value(setting, defaultValue=defaultValue)
            # Check if the type is stored in QSettings
            type_key = f"type_{setting}_type"
            type_str = self.qsettings.value(type_key, None)

            if type_str is not None and type(loaded_value).__name__ != type_str:
                try:
                    loaded_value = literal_eval(loaded_value)
                except (SyntaxError, ValueError):
                    if loaded_value in ["true", "false"]:
                        loaded_value = loaded_value == "true"
                    else:
                        return self.get_default(setting)
            if loaded_value is None:
                if defaultValue is None:
                    return self.get_default(setting)
                else:
                    return defaultValue
            else:
                return loaded_value
        else:
            self.load_settings()
            if setting in self.settings:
                return self.settings[setting]
            if defaultValue is None:
                return self.get_default(setting)
            else:
                return defaultValue

    def setValue(self, setting, value):
        if type(value) not in self.supported_types:
            raise TypeError(
                f"Unsupported type {type(value)} for setting '{setting}'. "
                f"Supported types are: {self.supported_types}"
            )
        if gui_mode:
            value_type = type(value)
            self.qsettings.setValue(setting, value)
            # Store the type of the value in the QSettings too
            self.qsettings.setValue(f"type_{setting}_type", value_type.__name__)
        else:
            self.load_settings()
            self.settings[setting] = value
            self.write_settings()

    def sync(self):
        if gui_mode:
            self.qsettings.sync()
        else:
            self.write_settings()
            self.load_settings()

    def childKeys(self):
        if gui_mode:
            return self.qsettings.childKeys()
        else:
            self.load_settings()
            return self.settings.keys()

    def remove(self, setting):
        if gui_mode:
            self.qsettings.remove(setting)
        else:
            self.load_settings()
            self.settings.pop(setting, None)
            self.write_settings()
