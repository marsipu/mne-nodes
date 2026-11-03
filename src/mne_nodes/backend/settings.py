"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import json
import os
import sys
import tomllib
from copy import deepcopy
from importlib.resources import files
from pathlib import Path
from types import NoneType
from typing import Any

from filelock import FileLock, Timeout

from mne_nodes import resources
from mne_nodes.backend.io import TypedJSONEncoder, type_json_hook

settings_config: dict[str, dict[str, Any]] = tomllib.loads(
    (files(resources) / "settings.toml").read_text(encoding="utf-8")
)

# Default device specific settings (formerly partly stored in QSettings)
# User-editable defaults and descriptions are defined in resources/settings.toml.
# Keep values JSON-serializable (TypedJSONEncoder handles Path objects).
default_device_settings = {
    "config_path": None,  # Last used project config file
    "plugin_config": {},  # Plugins and their config-paths
    "disabled_plugins": [],  # Plugin names disabled on this device
    "log_file_path": None,  # Optional custom log file path
    "bids_root": None,  # BIDS root directory
    "deriv_root": None,  # BIDS derivatives root directory
    "subjects_dirs": {},  # FreeSurfer directory overrides keyed by BIDS root
    "plot_root": None,  # Plot export root directory
    "plot_root_is_config_specific": False,  # Root already includes the config name
    "wsl_distribution": None,  # None uses the default WSL distribution
    "use_qthread": 1,  # Kept for backwards compatibility
    "save_ram": 1,  # Memory optimization flag
    "enable_cuda": 0,  # GPU usage flag
    "screen_name": None,  # Preferred screen / monitor name
    "app_theme": "auto",  # UI theme (auto/light/dark/high_contrast)
    "app_style": "fusion",  # Qt style
    "app_font": "Calibri",  # Default application font family
    "app_font_size": 12,  # Default application font size
    "keep_plots_open": True,  # Keep plot windows open after a pipeline finished
    "pipe_layout": "curved",  # Node-viewer pipe style (curved/straight/angle/routed)
    "first_start": True,  # Flag indicating if this is the first start of the application
}
default_device_settings.update(
    {name: details["default"] for name, details in settings_config.items()}
)


def _platform_settings_path() -> Path:
    """Return an OS-appropriate path for the settings JSON file.

    Override: If the environment variable ``MNENODES_SETTINGS_DIR`` is set,
    use it (treat it as directory unless it ends with .json). This makes
    testing and sandboxing easier.
    """
    override = os.getenv("MNENODES_SETTINGS_DIR")
    if override:
        override_path = Path(override)
        if override_path.suffix.lower() == ".json":
            return override_path
        return override_path / "settings.json"
    if sys.platform.startswith("win"):
        base = Path(os.getenv("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:  # Linux / other POSIX
        base = Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "mne-nodes" / "settings.json"


class Settings:
    def __init__(self) -> None:
        self._defaults = default_device_settings.copy()
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
        self.settings_path: Path = _platform_settings_path()
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.settings_path.with_suffix(".lock")
        self.lock_timeout = 5  # seconds
        self.lock = FileLock(self.lock_path, timeout=self.lock_timeout, blocking=True)

    # ------------------------- IO Helpers ---------------------------
    def _load(self) -> dict:
        try:
            with self.lock:
                return self._load_locked()
        except Timeout:
            print(
                f"Could not acquire lock for settings after {self.lock_timeout} seconds. Using defaults."
            )
            return deepcopy(self._defaults)

    def _load_locked(self) -> dict:
        try:
            with open(self.settings_path, encoding="utf-8") as f:
                return json.load(f, object_hook=type_json_hook)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError, FileNotFoundError):
            self._save_locked(deepcopy(self._defaults))
            return deepcopy(self._defaults)

    def _save_locked(self, settings) -> None:
        tmp = self.settings_path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=4, cls=TypedJSONEncoder)
        os.replace(tmp, self.settings_path)

    # ------------------------- Public API ---------------------------
    def __contains__(self, key: str) -> bool:
        """Return whether a setting has a persisted value."""
        return key in self._load()

    def default(self, name: str) -> Any:
        return self._defaults.get(name)

    def get(self, key: str, default: Any = None) -> Any:
        settings = self._load()
        return settings.get(key, self.default(key) if default is None else default)

    def set(self, key: str, value: Any) -> None:
        if not any(isinstance(value, t) for t in self.supported_types):
            raise TypeError(
                f"Unsupported type {type(value)} for '{key}'. Supported: {self.supported_types}"
            )
        try:
            with self.lock:
                settings = self._load_locked()
                settings[key] = value
                self._save_locked(settings)
        except Timeout:
            print(
                f"Could not acquire lock for settings file after {self.lock_timeout} seconds. Changes not saved."
            )

    def remove(self, key: str) -> None:
        try:
            with self.lock:
                settings = self._load_locked()
                if key in settings:
                    settings.pop(key)
                    self._save_locked(settings)
        except Timeout:
            print(
                f"Could not acquire lock for settings file after {self.lock_timeout} seconds. Changes not saved."
            )

    def keys(self) -> list[str]:
        settings = self._load()
        return list(settings.keys())
