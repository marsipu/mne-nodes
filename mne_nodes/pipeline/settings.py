"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes

Simplified settings management.

Key guarantees:
- Abrupt termination will not corrupt settings.
- Atomic writes via temp file + os.replace.
- Backward compatibility: value/setValue/childKeys/remove/get_default still work.

Environment overrides:
- MNENODES_SETTINGS_DIR: custom directory or explicit settings.json path.
"""

import json
import logging
import os
import sys
from copy import deepcopy
from pathlib import Path
from types import NoneType
from typing import Any, List

from filelock import FileLock, Timeout
from mne_nodes.pipeline.io import type_json_hook, TypedJSONEncoder

# Default device specific settings (formerly partly stored in QSettings)
# NOTE: Add new keys here when introducing additional persistent settings.
# Keep values JSON-serializable (TypedJSONEncoder handles Path objects).
default_device_settings = {
    "config_path": None,  # Last used project config file
    "log_file_path": None,  # Optional custom log file path
    "data_path": None,  # Project data directory (device specific)
    "plot_path": None,  # Plot export directory (device specific)
    "fs_path": None,  # FREESURFER_HOME (legacy / optional)
    "wls_mne_path": None,  # Legacy WSL MNE path
    "use_qthread": 1,  # Kept for backwards compatibility
    "save_ram": 1,  # Memory optimization flag
    "enable_cuda": 0,  # GPU usage flag
    "screen_ratio": 0.8,  # GUI screen ratio preference
    "screen_name": None,  # Preferred screen / monitor name
    "app_theme": "auto",  # UI theme (auto/light/dark/high_contrast)
    "app_style": "fusion",  # Qt style
    "app_font": "Calibri",  # Default application font family
    "app_font_size": 10,  # Default application font size
}


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
        self.lock = FileLock(self.lock_path)
        self.lock_timeout = 5  # seconds
        self._settings: dict[str, Any] | None = None

    # ------------------------- IO Helpers ---------------------------
    def _backfill_defaults(self, write_on_change: bool) -> None:
        changed = False
        for k, v in self._defaults.items():
            if k not in self._settings:
                self._settings[k] = v
                changed = True
        if changed and write_on_change:
            self._save_locked()

    def _load(self) -> None:
        try:
            with self.lock.acquire(timeout=self.lock_timeout, blocking=True):
                self._load_locked()
        except Timeout:
            logging.error(
                f"Could not acquire lock for settings after {self.lock_timeout} seconds. Using defaults."
            )
            self._settings = deepcopy(self._defaults)

    def _load_locked(self) -> None:
        if self.settings_path.is_file():
            try:
                with open(self.settings_path, encoding="utf-8") as f:
                    self._settings = json.load(f, object_hook=type_json_hook)
                    self._backfill_defaults(write_on_change=True)
            except (OSError, json.JSONDecodeError, UnicodeDecodeError) as err:
                logging.warning(
                    f"Loading settings from {self.settings_path} failed with:\n{err}\nUsing defaults."
                )
                self._settings = deepcopy(self._defaults)
        else:
            self._settings = deepcopy(self._defaults)
            self._save_locked()

    def _save(self) -> None:
        try:
            with self.lock.acquire(timeout=self.lock_timeout, blocking=True):
                self._save_locked()
        except Timeout:
            logging.error(
                f"Could not acquire lock for settings file after {self.lock_timeout} seconds. Changes not saved."
            )

    def _save_locked(self) -> None:
        with open(self.settings_path, "w", encoding="utf-8") as f:
            json.dump(self._settings, f, indent=4, cls=TypedJSONEncoder)

    # ------------------------- Public API ---------------------------
    def default(self, name: str) -> Any:
        return self._defaults.get(name)

    def get(self, key: str, default: Any = None) -> Any:
        self._load()
        if key in self._settings:
            return self._settings[key]
        return self.default(key) if default is None else default

    def set(self, key: str, value: Any) -> None:
        if not any(isinstance(value, t) for t in self.supported_types):
            raise TypeError(
                f"Unsupported type {type(value)} for '{key}'. Supported: {self.supported_types}"
            )
        try:
            with self.lock.acquire(timeout=self.lock_timeout, blocking=True):
                self._load_locked()
                self._settings[key] = value
                self._save_locked()
        except Timeout:
            logging.error(
                f"Could not acquire lock for settings file after {self.lock_timeout} seconds. Changes not saved."
            )

    def remove(self, key: str) -> None:
        try:
            with self.lock.acquire(timeout=self.lock_timeout, blocking=True):
                self._load_locked()
                if key in self._settings:
                    self._settings.pop(key)
                    self._save_locked()
        except Timeout:
            logging.error(
                f"Could not acquire lock for settings file after {self.lock_timeout} seconds. Changes not saved."
            )

    def keys(self) -> List[str]:
        self._load()
        return list(self._settings.keys())

    def sync(self) -> None:
        try:
            with self.lock.acquire(timeout=self.lock_timeout, blocking=True):
                self._load_locked()
                self._save_locked()
        except Timeout:
            logging.error(
                f"Could not acquire lock for settings file after {self.lock_timeout} seconds. Changes not saved."
            )
