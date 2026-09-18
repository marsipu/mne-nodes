"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import ast
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from copy import deepcopy
from functools import partial
from importlib import import_module
from importlib.util import cache_from_source
from inspect import getsource
from os.path import isdir, isfile, join
from pathlib import Path
from time import perf_counter
from types import ModuleType
from typing import Any

import mne
from filelock import FileLock, Timeout
from mne_bids import (
    BIDSPath,
    get_bids_path_from_fname,
    get_datatypes,
    get_entity_vals,
    read_raw_bids,
)

from mne_nodes import _widgets, ismac, iswin
from mne_nodes.gui.gui_utils import (
    ask_user,
    ask_user_custom,
    get_user_input,
    question_yes_no,
    raise_user_attention,
)
from mne_nodes.logger import logger
from mne_nodes.pipeline.code_generation import CodeGenerator
from mne_nodes.pipeline.io import TypedJSONEncoder, load_json
from mne_nodes.pipeline.package_utils import (
    get_name_from_github,
    import_distribution,
    install_github_package,
    install_pip_packages,
)
from mne_nodes.pipeline.pipeline_utils import is_test
from mne_nodes.pipeline.settings import Settings

default_config = {
    # BIDS
    "selected_inputs": {
        "file": [],
        "subject": [],
    },  # BIDS entity values as keys for lists
    "group_by": "subject",
    "custom_groups": {},
    "bids_dataset_name": None,  # Cached BIDS dataset name from dataset_description.json
    # Parameters
    "parameters": {},
    # Pipelined Configuration
    "show_plots": True,
    "save_plots": True,
    "overwrite": False,
    "shutdown": False,
    # Plugins
    "plugin_meta": {},
    "functions": {},
    # Nodes
    "node_config": {"nodes": {}, "connections": {}},
}


class Controller:
    """This is the central organizing structure of a mne-nodes project.
    It stores all (device-independent) information, to change project set another config_path.

    Parameters
    ----------
    config_path : str or Path, optional
        Path to the config-file.
    settings : Settings, optional
        Settings object to use for device-dependent settings.
    """

    def __init__(
        self, config_path: str | Path | None = None, settings: Settings | None = None
    ):
        self.settings = settings or Settings()
        # These hidden attributes should not be set directly
        self._config = deepcopy(default_config)
        self._config_path: Path | None = None
        self._config_lock = None
        self._last_load = 0
        self._local_set = False
        self.plugins = {}
        self.function_meta = {}
        self.lock_timeout = 5  # seconds
        self.disk_interval = 10  # seconds
        # raw datatypes
        self.raw_types = ["eeg", "meg", "ieeg"]
        # possible scopes for grouping and selection
        self.scopes = ["subject", "session", "run", "task", "custom"]
        self._process_count = 0
        # Initialize config_path here without prompting. Interactive setup is
        # handled explicitly via ensure_* methods after QApplication startup.
        self._initialize_startup_config_path(config_path)
        # Initialize plugins
        self.load_recent_plugins()

    ####################################################################################
    # Initialization and Properties
    ####################################################################################
    @property
    def config_path(self) -> Path | None:
        """Path to the config-file."""
        if self._config_path is not None:
            return self._config_path
        return self._setting_file("config_path")

    def _resolve_startup_config_path(self, config_path: Any) -> Path | None:
        startup_path = config_path
        if startup_path is None:
            startup_path = self.settings.get("config_path", default=None)
        startup_path = self._as_path(startup_path)
        if startup_path is None:
            return None
        if startup_path.is_file():
            return startup_path
        logger.warning(f"Config file {startup_path} does not exist!")
        return None

    def _initialize_startup_config_path(self, config_path: Any) -> None:
        startup_path = self._resolve_startup_config_path(config_path)
        if startup_path is not None:
            self._set_config_path(startup_path, reprompt_on_none=False)

    def _prompt_config_path(self) -> Path:
        ans = ask_user_custom(
            "Do you want to create a new config-file or use an existing one?",
            buttons=("Create new", "Use existing"),
            close_on_cancel=True,
        )
        if ans is None:  # user cancelled
            logger.info("User canceled, closing app.")
            sys.exit(0)
        if ans:
            logger.info("Creating new config-file.")
            config_folder = self._as_path(
                get_user_input(
                    "Set the folder-path to store the config-file",
                    input_type="folder",
                    exit_on_cancel=True,
                )
            )
            name = get_user_input(
                "Please enter a name for this project", input_type="string"
            )
            if config_folder is None or name is None:
                raise RuntimeError("Config path initialization failed.")
            # Keep project name first in JSON for readability.
            config = {"name": name, **deepcopy(default_config)}
            config_path = config_folder / f"{name}_config.json"
            with open(config_path, "w", encoding="utf-8") as file:
                json.dump(config, file, indent=4, cls=TypedJSONEncoder)
                logger.info(f"New configuration created at:\n{config_path}")
            return config_path

        logger.info("Using existing config-file.")
        config_path = self._as_path(
            get_user_input(
                "Please enter the path to an existing config-file",
                input_type="file",
                file_filter="JSON files (*.json)",
                exit_on_cancel=True,
            )
        )
        if config_path is None:
            raise RuntimeError("Config path initialization failed.")
        logger.info(f"Configuration sucessfully loaded from:\n{config_path}")
        return config_path

    def _normalize_config_path(self, config_path: Any) -> Path:
        config_path = self._as_path(config_path)
        if config_path is None:
            raise RuntimeError("Failed to resolve config file path.")
        if config_path.suffix.lower() != ".json":
            config_path = config_path.with_suffix(".json")
        return config_path

    def _activate_config_path(self, config_path: Any) -> Path:
        config_path = self._normalize_config_path(config_path)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        self._config_path = config_path
        self._config_lock = FileLock(self._config_path.with_suffix(".lock"))
        self.settings.set("config_path", self._config_path)
        return self._config_path

    def _apply_config_path(self, config_path: Path) -> None:
        self._activate_config_path(config_path)
        if self._config_path.is_file():
            self.load(nodes=True, plugins=True)
        else:
            self.flush()

    def _set_config_path(self, value: Any, *, reprompt_on_none: bool = False) -> Path:
        config_path = self._set_setting_file(
            key="config_path",
            value=value,
            prompt=self._prompt_config_path,
            missing_message=(
                "Config file {path} does not exist! If you moved from another "
                "device, please select/create the correct config-file."
            ),
            reprompt_on_none=reprompt_on_none,
        )
        self._apply_config_path(config_path)
        return config_path

    @config_path.setter
    def config_path(self, value):
        """Set the path to the config-file (respects interactive mode)."""
        self._set_config_path(value, reprompt_on_none=True)

    @property
    def config_lock(self):
        if self._config_lock is None:
            raise RuntimeError(
                "Config path is not initialized. Call ensure_config_path() first."
            )
        return self._config_lock

    @staticmethod
    def _as_path(value: Any) -> Path | None:
        if value is None:
            return None
        if isinstance(value, (str, os.PathLike, Path)):
            return Path(value)
        return None

    def _setting_folder(self, key: str) -> Path | None:
        path_value = self._as_path(self.settings.get(key, None))
        if path_value is not None and path_value.is_dir():
            return path_value
        return None

    def _setting_file(self, key: str) -> Path | None:
        path_value = self._as_path(self.settings.get(key, None))
        if path_value is not None and path_value.is_file():
            return path_value
        return None

    @staticmethod
    def _validate_existing_dir(value: Any, *, key: str) -> Path:
        path_value = Controller._as_path(value)
        if path_value is None or not path_value.is_dir():
            raise ValueError(f"Path {value} does not exist for '{key}'!")
        return path_value

    def _prompt_path(self, prompt: str) -> Path:
        selected_path = self._as_path(
            get_user_input(prompt, "folder", cancel_allowed=False)
        )
        if selected_path is None:
            raise RuntimeError("Failed to initialize required path.")
        return selected_path

    def _ensure_setting_path(
        self, *, key: str, prompt: str, missing_message: str, interactive: bool
    ) -> Path:
        configured_path = self._as_path(self.settings.get(key, None))
        if configured_path is not None and configured_path.is_dir():
            return configured_path
        if configured_path is not None:
            logger.warning(missing_message.format(path=configured_path))
            if interactive:
                raise_user_attention(missing_message.format(path=configured_path))
        if not interactive:
            raise RuntimeError(
                f"Required path '{key}' is not configured. Call ensure_{key}() first."
            )
        selected_path = self._as_path(
            get_user_input(prompt, "folder", cancel_allowed=False)
        )
        if selected_path is None:
            raise RuntimeError(f"Failed to initialize required path '{key}'.")
        self.settings.set(key, selected_path)
        return selected_path

    def _ensure_setting_file(
        self,
        *,
        key: str,
        prompt: Callable[[], Path],
        missing_message: str,
        interactive: bool,
    ) -> Path:
        configured_path = self._as_path(self.settings.get(key, None))
        if configured_path is not None and configured_path.is_file():
            return configured_path
        if configured_path is not None:
            logger.warning(missing_message.format(path=configured_path))
            if interactive:
                raise_user_attention(missing_message.format(path=configured_path))
        if not interactive:
            raise RuntimeError(
                f"Required file '{key}' is not configured. Call ensure_{key}() first."
            )
        selected_path = self._as_path(prompt())
        if selected_path is None:
            raise RuntimeError(f"Failed to initialize required file '{key}'.")
        if selected_path.is_dir():
            raise ValueError(
                f"Path {selected_path} is a directory, expected a file path."
            )
        self.settings.set(key, selected_path)
        return selected_path

    def _set_setting_path(
        self,
        *,
        key: str,
        value: Any,
        prompt: str,
        missing_message: str,
        reprompt_on_none: bool = False,
    ) -> Path:
        if value is None:
            if reprompt_on_none:
                selected_path = self._prompt_path(prompt)
                self.settings.set(key, selected_path)
                return selected_path
            return self._ensure_setting_path(
                key=key,
                prompt=prompt,
                missing_message=missing_message,
                interactive=True,
            )
        path_value = self._validate_existing_dir(value, key=key)
        self.settings.set(key, path_value)
        return path_value

    def _set_setting_file(
        self,
        *,
        key: str,
        value: Any,
        prompt: Callable[[], Path],
        missing_message: str,
        reprompt_on_none: bool = False,
    ) -> Path:
        if value is None:
            if reprompt_on_none:
                selected_path = self._as_path(prompt())
                if selected_path is None:
                    raise RuntimeError(f"Failed to initialize required file '{key}'.")
                if selected_path.is_dir():
                    raise ValueError(
                        f"Path {selected_path} is a directory, expected a file path."
                    )
                self.settings.set(key, selected_path)
                return selected_path
            return self._ensure_setting_file(
                key=key,
                prompt=prompt,
                missing_message=missing_message,
                interactive=True,
            )

        path_value = self._as_path(value)
        if path_value is None:
            raise RuntimeError(f"Failed to initialize required file '{key}'.")
        if path_value.is_dir():
            raise ValueError(f"Path {path_value} is a directory, expected a file path.")
        self.settings.set(key, path_value)
        return path_value

    def _get_subjects_dir_path(self) -> Path | None:
        if is_test():
            subjects_dir = self.settings.get("subjects_dir", None)
        else:
            subjects_dir = mne.get_config("SUBJECTS_DIR", None)
        subjects_dir = self._as_path(subjects_dir)
        if subjects_dir is not None and subjects_dir.is_dir():
            return subjects_dir
        return None

    def _set_subjects_dir_path(self, value: Path) -> None:
        if is_test():
            self.settings.set("subjects_dir", value)
        else:
            mne.set_config("SUBJECTS_DIR", value)

    def _prompt_name(self) -> str:
        name = get_user_input(
            "Please enter a name for this project", "string", cancel_allowed=False
        )
        if name is None:
            raise RuntimeError("Project name initialization failed.")
        return str(name)

    @property
    def name(self) -> str | None:
        return self.get("name", None)

    @name.setter
    def name(self, new_name):
        if new_name is None:
            new_name = self._prompt_name()
        else:
            new_name = str(new_name)
        old_name = self.get("name")
        if old_name != new_name and self._config_path is not None:
            # Rename the config file if the name changes
            old_path = self._config_path
            new_path = self._config_path.parent / f"{new_name}_config.json"
            os.rename(old_path, new_path)
            self._config_path = new_path
        self.set("name", new_name)

    @property
    def bids_root(self) -> Path | None:
        """Configured BIDS root directory, if available."""
        return self._setting_folder("bids_root")

    @bids_root.setter
    def bids_root(self, value: Any) -> None:
        previous_root = self.bids_root
        new_root = self._set_setting_path(
            key="bids_root",
            value=value,
            prompt="Please select/create a folder for the bids-root.",
            missing_message=(
                "Path {path} does not exist! If you moved from another device, "
                "please select the bids-root folder."
            ),
            reprompt_on_none=True,
        )
        if previous_root == new_root:
            return
        if previous_root != new_root:
            ans = ask_user(
                "When you change the BIDS-root, all selections, custom groups, "
                "derivatives-root and plot-root will be lost. Do you want to proceed?"
            )
            if not ans:
                self.settings.set("bids_root", previous_root)
                return

        # Clear selected inputs and custom groups
        selected_inputs = self.get("selected_inputs")
        custom_groups = self.get("custom_groups")
        selected_inputs.clear()
        custom_groups.clear()
        selected_inputs.update(deepcopy(default_config["selected_inputs"]))
        custom_groups.update(deepcopy(default_config["custom_groups"]))
        self.set("selected_inputs", selected_inputs)
        self.set("custom_groups", custom_groups)
        # deriv_root/plot_root belonged to the previous dataset, force re-selection
        self.settings.set("deriv_root", None)
        self.settings.set("plot_root", None)
        # Update input widget when viewer is available.
        if self.viewer is not None:
            self.viewer.input_node.update_widgets()

    @property
    def deriv_root(self) -> Path | None:
        """Configured derivatives root directory, if available."""
        return self._setting_folder("deriv_root")

    @deriv_root.setter
    def deriv_root(self, value: Any) -> None:
        self._set_setting_path(
            key="deriv_root",
            value=value,
            prompt="Please select/create a folder for the derivatives root.",
            missing_message=(
                "Path {path} does not exist! If you moved from another device, "
                "please select the correct folder for data derivatives."
            ),
            reprompt_on_none=True,
        )

    @property
    def subjects_dir(self) -> Path | None:
        """Configured FreeSurfer subjects directory, if available."""
        return self._get_subjects_dir_path()

    @subjects_dir.setter
    def subjects_dir(self, value):
        if value is None:
            selected_path = self._prompt_path(
                "Please enter the path to the FreeSurfer subjects directory"
            )
            self._set_subjects_dir_path(selected_path)
            return
        selected_path = self._validate_existing_dir(value, key="subjects_dir")
        self._set_subjects_dir_path(selected_path)

    @property
    def plot_root(self) -> Path | None:
        """Configured plot output directory, if available."""
        return self._setting_folder("plot_root")

    @plot_root.setter
    def plot_root(self, value):
        self._set_setting_path(
            key="plot_root",
            value=value,
            prompt="Please select/create a folder for saving plots.",
            missing_message=(
                "Path {path} does not exist! If you moved from another device, "
                "please select/create the folder where plots should be saved."
            ),
            reprompt_on_none=True,
        )

    @property
    def plot_path(self) -> Path:
        """Path to the plot directory for the current project."""
        plot_root = self.ensure_plot_root(interactive=False)
        name = self.ensure_name(interactive=False)
        plot_path = plot_root / name
        if not isdir(plot_path):
            plot_path.mkdir(parents=True, exist_ok=True)
        return plot_path

    def ensure_config_path(self, interactive: bool = True) -> Path:
        if self._config_path is not None:
            return self._config_path
        config_path = self._ensure_setting_file(
            key="config_path",
            prompt=self._prompt_config_path,
            missing_message=(
                "Config file {path} does not exist! If you moved from another "
                "device, please select/create the correct config-file."
            ),
            interactive=interactive,
        )
        self._apply_config_path(config_path)
        return config_path

    def ensure_name(self, interactive: bool = True) -> str:
        name = self.get("name", None)
        if isinstance(name, str):
            return name
        if name is not None:
            coerced_name = str(name)
            self.set("name", coerced_name)
            return coerced_name
        if not interactive:
            raise RuntimeError(
                "Project name is not initialized. Call ensure_name() first."
            )
        coerced_name = self._prompt_name()
        self.name = coerced_name
        return coerced_name

    def ensure_bids_root(self, interactive: bool = True) -> Path:
        return self._ensure_setting_path(
            key="bids_root",
            prompt="Please select/create a folder for the bids-root.",
            missing_message=(
                "Path {path} does not exist! If you moved from another device, "
                "please select the bids-root folder."
            ),
            interactive=interactive,
        )

    def ensure_deriv_root(self, interactive: bool = True) -> Path:
        return self._ensure_setting_path(
            key="deriv_root",
            prompt="Please select/create a folder for the derivatives root.",
            missing_message=(
                "Path {path} does not exist! If you moved from another device, "
                "please select the correct folder for data derivatives."
            ),
            interactive=interactive,
        )

    def ensure_plot_root(self, interactive: bool = True) -> Path:
        return self._ensure_setting_path(
            key="plot_root",
            prompt="Please select/create a folder for saving plots.",
            missing_message=(
                "Path {path} does not exist! If you moved from another device, "
                "please select/create the folder where plots should be saved."
            ),
            interactive=interactive,
        )

    def ensure_subjects_dir(self, interactive: bool = True) -> Path:
        subjects_dir = self.subjects_dir
        if subjects_dir is not None:
            return subjects_dir
        if not interactive:
            raise RuntimeError(
                "FreeSurfer subjects directory is not configured. Call ensure_subjects_dir() first."
            )
        selected_path = self._prompt_path(
            "Please enter the path to the FreeSurfer subjects directory"
        )
        self.subjects_dir = selected_path
        return selected_path

    def run_freesurfer_subprocess(self, command: list[str]) -> None:
        """Run a FreeSurfer/MNE command using paths from controller settings."""
        if len(command) == 0:
            raise ValueError("Command must not be empty.")

        fs_path_value = self.settings.get("fs_path", None)
        if fs_path_value is None:
            raise RuntimeError(
                "Path to FREESURFER_HOME not set, can't run this function"
            )
        fs_path = str(fs_path_value)
        subjects_dir = str(self.ensure_subjects_dir(interactive=False))
        mne_path = self.settings.get("mne_path", None) or self.settings.get(
            "wls_mne_path", None
        )

        environment = os.environ.copy()
        environment["FREESURFER_HOME"] = fs_path
        environment["SUBJECTS_DIR"] = subjects_dir

        command_line = list(command)
        if iswin:
            command_line.insert(0, "wsl")
            if mne_path is None:
                raise RuntimeError(
                    "Path to MNE environment in WSL not set, can't run this function"
                )
            environment["PATH"] = (
                f"{fs_path}/bin:{mne_path}/bin:"
                f"/usr/local/sbin:"
                f"/usr/local/bin:"
                f"/usr/sbin:"
                f"/usr/bin:"
                f"/sbin:"
                f"/bin"
            )
            environment["WSLENV"] = "PATH/u:SUBJECTS_DIR/p:FREESURFER_HOME/u"
        else:
            environment["PATH"] = environment["PATH"] + f":{fs_path}/bin"

        if ismac:
            if isdir(join(fs_path, "lib/misc/lib")):
                environment["PATH"] = environment["PATH"] + f":{fs_path}/lib/misc/bin"
                environment["MISC_LIB"] = join(fs_path, "lib/misc/lib")
                environment["LD_LIBRARY_PATH"] = join(fs_path, "lib/misc/lib")
                environment["DYLD_LIBRARY_PATH"] = join(fs_path, "lib/misc/lib")

            if isdir(join(fs_path, "lib/gcc/lib")):
                environment["DYLD_LIBRARY_PATH"] = join(fs_path, "lib/gcc/lib")

        process = subprocess.Popen(
            command_line,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            universal_newlines=True,
        )

        if process.stdout is not None:
            for stdout_line in process.stdout:
                if stdout_line:
                    sys.stdout.write(stdout_line)

        return_code = process.wait()
        if return_code != 0:
            raise RuntimeError(
                f"FreeSurfer command failed with exit code {return_code}: {' '.join(command_line)}"
            )

    def ensure_ready(
        self,
        *,
        required: tuple[str, ...] = ("config_path", "bids_root", "deriv_root"),
        interactive: bool = True,
    ) -> None:
        missing = []
        ensure_map = {
            "config_path": self.ensure_config_path,
            "name": self.ensure_name,
            "bids_root": self.ensure_bids_root,
            "deriv_root": self.ensure_deriv_root,
            "plot_root": self.ensure_plot_root,
            "subjects_dir": self.ensure_subjects_dir,
        }
        for item in required:
            ensure_func = ensure_map.get(item)
            if ensure_func is None:
                raise ValueError(f"Unknown required controller state: {item}")
            try:
                ensure_func(interactive=interactive)
            except RuntimeError:
                missing.append(item)
        if missing:
            missing_str = ", ".join(missing)
            raise RuntimeError(f"Missing required controller state: {missing_str}")

    @staticmethod
    def default(key):
        """Get the default value for a specific key."""
        return deepcopy(default_config.get(key, None))

    def _check_bids_root_mismatch(self, config: dict) -> None:
        """Warn and reset device paths if bids_root doesn't match the loaded project.

        ``bids_root``, ``deriv_root`` and ``plot_root`` are device-wide settings,
        shared across all config-files/projects on this device. If the currently
        configured ``bids_root`` points to a different dataset than the one this
        project was last used with (recorded as ``bids_dataset_name``), the
        selection/derivatives/plot paths are stale and must be re-selected.
        """
        cached_name = config.get("bids_dataset_name")
        if not cached_name:
            return
        bids_root = self._setting_folder("bids_root")
        if bids_root is None:
            return
        actual_name = self._read_bids_dataset_name(bids_root)
        if actual_name is None or actual_name == cached_name:
            return
        raise_user_attention(
            f"The configured BIDS-root '{bids_root}' belongs to dataset "
            f"'{actual_name}', but this project was last used with dataset "
            f"'{cached_name}'. Please select the correct bids-root, "
            "derivatives-root and plot-root for this project.",
            "warning",
        )
        for key in ("bids_root", "deriv_root", "plot_root"):
            self.settings.set(key, None)

    def _load_config(self, *, nodes: bool = False, plugins: bool = False):
        """Load config from disk and optionally resolve nodes and pipeline dependencies."""
        config_path = self.ensure_config_path(interactive=False)
        try:
            config = load_json(config_path, no_gui=True)
        except (
            OSError,
            json.JSONDecodeError,
            UnicodeDecodeError,
            FileNotFoundError,
        ) as err:
            logger.warning(
                f"Loading config from {config_path} failed with:\n{err}\nUsing defaults."
            )
            config = deepcopy(default_config)

        if not isinstance(config, dict):
            logger.warning("Loaded configuration has invalid type. Using defaults.")
            config = deepcopy(default_config)

        self._check_bids_root_mismatch(config)

        if nodes and self.viewer is not None:
            self.viewer.load_nodes(config["node_config"])
        return config

    def load(self, *, nodes: bool = False, plugins: bool = False):
        """Force loading the config from disk.

        Parameters
        ----------
        nodes : bool
            If True, load node-configuration into the node-viewer
        plugins : bool
            If True, resolve plugin dependencies declared in the loaded config
            (including pip plugin installs for missing plugins).
        """
        if self._config_path is None:
            logger.debug("Config path is not set. Keeping in-memory configuration.")
            return
        try:
            with self.config_lock:
                self._config = self._load_config(nodes=nodes, plugins=plugins)
                if plugins and self.viewer:
                    self.load_recent_plugins()
            self._last_load = perf_counter()
            self._local_set = False

        except Timeout:
            logger.warning(
                f"Could not acquire lock for settings after {self.lock_timeout} seconds."
            )

    def flush(self):
        """Force writing the current config to disk."""
        if self._config_path is None:
            logger.debug("Config path is not set. Skipping config flush.")
            return
        try:
            with self.config_lock:
                config_path = self.ensure_config_path(interactive=False)
                config_to_save = deepcopy(self._config)
                with open(config_path, "w") as file:
                    json.dump(config_to_save, file, indent=4, cls=TypedJSONEncoder)
        except Timeout:
            logger.error(
                f"Could not acquire lock for settings file after {self.lock_timeout} seconds. Changes not saved."
            )

    def get(self, key, default=None) -> Any:
        """Load a specific key from the config-file."""
        now = perf_counter()
        if self._config_path is not None and (
            self._config is None
            or (not self._local_set and now - self._last_load > self.disk_interval)
        ):
            self._last_load = now
            self.load()
        value = self._config.get(key, self.default(key) if default is None else default)
        return value

    def _delayed_flush(self):
        if self._config_path is None:
            self._local_set = True
            return
        now = perf_counter()
        if now - self._last_load > self.disk_interval:
            self._last_load = now
            self.flush()
            self._local_set = False
        else:
            # Make sure when setting a variable to config without writing to disk, that it is not overwritten by a load from disk.
            self._local_set = True

    def set(self, key, value) -> None:
        """Set a specific key in the config-file."""
        self._config[key] = value
        self._delayed_flush()

    def set_dict_value(self, config_name, key, value):
        """Set a specific key in a dictionary within the config-file."""
        if config_name not in self._config:
            self._config[config_name] = {}
        self._config[config_name][key] = value
        self._delayed_flush()

    @property
    def run_script_folder(self):
        """Path to the local config folder."""
        local_config_path = Path.home() / ".mne-nodes"
        local_config_path.mkdir(parents=True, exist_ok=True)

        return local_config_path

    @property
    def viewer(self):
        """Get the viewer object from the _widgets dictionary."""
        return _widgets.get("viewer", None)

    @property
    def main_window(self):
        """Get the main window object from the _widgets dictionary."""
        main_window = _widgets.get("main_window", None)
        if main_window is None:
            raise RuntimeError(
                "Main window is not initialized. Please initialize the main window first."
            )
        return main_window

    ####################################################################################
    # BIDS
    ####################################################################################
    @staticmethod
    def _read_bids_dataset_name(bids_root: Path) -> str | None:
        """Read the dataset name from a bids-root's dataset_description.json."""
        dataset_file = bids_root / "dataset_description.json"
        if not dataset_file.is_file():
            logger.warning(f"Dataset description file not found at {dataset_file}.")
            return None
        return load_json(dataset_file, no_gui=True).get("Name")

    def get_dataset_name(self) -> str | None:
        try:
            bids_root = self.ensure_bids_root(interactive=False)
        except RuntimeError:
            bids_root = None
        if bids_root is not None:
            name = self._read_bids_dataset_name(bids_root)
            if name is not None:
                self.set("bids_dataset_name", name)
                return name
        # Fall back to cached value from config
        return self.get("bids_dataset_name", None)

    def get_group_by(self, group_by):
        if group_by == "custom":
            data = {
                k: [get_bids_path_from_fname(i) for i in v]
                for k, v in self.get("custom_groups").items()
            }
        else:
            vals = get_entity_vals(self.bids_root, group_by)
            # ToDo: This might need to get generalized when adapting to other formats
            data = {
                v: [
                    bp
                    for bp in BIDSPath(**{group_by: v, "root": self.bids_root}).match(
                        ignore_json=True, ignore_nosub=True
                    )
                    if bp.datatype in self.raw_types and bp.extension != ".tsv"
                ]
                for v in vals
            }

        return data

    def get_group_by_strings(self, group_by):
        data = {
            v: [bp.basename for bp in items]
            for v, items in self.get_group_by(group_by).items()
        }

        return data

    def get_fsmri_subjects(self):
        fsmri_subjects = (
            os.listdir(self.subjects_dir) if self.subjects_dir is not None else []
        )
        return fsmri_subjects

    def get_datatypes(self):
        # ToDo: Implement data-types other than raw
        bids_root = self.ensure_bids_root(interactive=False)
        excluded_datatypes = ["func"]
        return [dt for dt in get_datatypes(bids_root) if dt not in excluded_datatypes]

    def get_datatype_items(self):
        items = {}
        data_types = self.get_datatypes()
        for dt in data_types:
            bp_kwargs = {"root": self.bids_root, "check": False}
            if dt in self.raw_types:
                bp_kwargs.update({"suffix": dt})
            else:
                bp_kwargs.update({"datatype": dt})
            items[dt] = [
                f.basename for f in BIDSPath(**bp_kwargs).match(ignore_json=True)
            ]
        return items

    def input_selection_changed(self, selected, data_type):
        selected_inputs = self.get("selected_inputs")
        selected_inputs[data_type] = selected
        self.set("selected_inputs", selected_inputs)
        self.check_selection_enable()

    def check_selection_enable(self):
        # Enable/Disable start buttons based on whether any inputs are selected
        any_selected = any(len(v) > 0 for v in self.get("selected_inputs").values())
        if self.viewer is not None:
            self.viewer.enable_start_buttons(any_selected)

    def load_raw(self, items):
        """Load raw data and event-id for one or multiple bids-paths.

        Parameters
        ----------
        items : BIDSPath | list[BIDSPath]
            A single bids-path (file-target) or a list of bids-paths
            (group-target).

        Returns
        -------
        raw, event_id
            If `items` is a single bids-path, a ``(raw, event_id)`` tuple.
            If `items` is a list, a tuple of two lists ``(raw_list,
            event_id_list)`` with one raw/event_id per member.
        """

        def _load(bp, preload=True):
            bp = bp.copy().update(root=self.bids_root)
            return read_raw_bids(
                bp, extra_params={"preload": preload}, return_event_dict=True
            )

        if isinstance(items, list):
            loaded = [_load(bp, preload=True) for bp in items]
            return [r for r, _ in loaded], [e for _, e in loaded]
        return _load(items, preload=True)

    def load_info(self, items, raw=None):
        """Load measurement info for one or multiple bids-paths.

        Parameters
        ----------
        items : BIDSPath | list[BIDSPath]
            A single bids-path (file-target) or a list of bids-paths
            (group-target).
        raw : mne.io.Raw | Iterable[mne.io.Raw] | None
            Already loaded raw data(s) to take the info from, matching the
            shape of `items`. If None, info is read from disk directly.

        Returns
        -------
        info
            If `items` is a single bids-path, an `mne.Info` instance.
            If `items` is a list, a list of `mne.Info` instances, one per
            member.
        """

        def _load(bp):
            bp = bp.copy().update(root=self.bids_root)
            return mne.io.read_info(bp.fpath)

        if isinstance(items, list):
            if raw is not None:
                return [r.info for r in raw]
            return [_load(bp) for bp in items]
        if raw is not None:
            return raw.info
        return _load(items)

    def load_subject(self, subject):
        result = subject in self.get_fsmri_subjects()
        if not result:
            logger.warning(
                f"Subject {subject} not found in FreeSurfer subjects directory!"
            )
            return False
        return subject

    ####################################################################################
    # Parameters
    ####################################################################################
    def get_default(self, parameter_name: str, function_name: str) -> Any:
        """Get the default value for a given parameter name."""
        parameter_meta = self.get_parameter_meta(parameter_name, function_name)

        return parameter_meta["default"]

    def parameter(self, parameter_name: str, function_name: str) -> Any:
        """Get a specific parameter from the project parameters."""
        parameters = self.get("parameters")
        if parameter_name == "subjects_dir":
            return self.subjects_dir
        elif parameter_name not in parameters.get(function_name, {}):
            # logger.debug(
            #     f"Parameter '{parameter_name}' not found in project for function '{function_name}'. Setting default value."
            # )
            value = self.get_default(parameter_name, function_name)
            self.set_parameter(parameter_name, value, function_name)
            return value

        return parameters[function_name][parameter_name]

    def set_parameter(
        self, parameter_name: str, value: Any, function_name: str
    ) -> None:
        """Set a specific parameter in the project parameters."""
        parameters = self.get("parameters")
        if function_name not in parameters:
            parameters[function_name] = {}
        parameters[function_name][parameter_name] = value
        self.set("parameters", parameters)

    def func_inputs(
        self, function_name: str, loaded_data: list
    ) -> tuple[dict[str, str], list[str]]:
        """Get the inputs to pass to a function from the loaded data.

        Returns
        -------
        tuple[dict[str, str], list[str]]
            - Mapping of function parameter name to the loaded variable name
              to pass for it. Parameter and variable name differ when the
              loaded data matches via ``accepted_ports`` instead of the
              parameter name itself (e.g. parameter ``all_inst`` accepting a
              loaded ``evoked``).
            - Parameter names not yet satisfied by ``loaded_data``, which
              still need to be loaded (e.g. from disk) under their own name.
        """
        func_meta = self.get_function_meta(function_name)
        input_map = {}
        loading_needed = []
        for i, v in func_meta.get("inputs", {}).items():
            if i in loaded_data:
                input_map[i] = i
                continue
            matched = next(
                (a for a in v.get("accepted_ports") or [] if a in loaded_data), None
            )
            if matched is not None:
                input_map[i] = matched
            else:
                loading_needed.append(i)
        return input_map, loading_needed

    def get_load_meta_for_port(self, port_name: str) -> dict[str, Any] | None:
        """Find load metadata for a data/port name across all known functions.

        A function's own input may accept a port name (e.g. ``evoked``) without
        declaring how to load it from disk itself. This searches every
        function's inputs for one that both is loadable (has a ``read`` key)
        and matches ``port_name`` (its own key or via ``accepted_ports``).

        Returns
        -------
        dict | None
            The matching input metadata, or ``None`` if no loadable input is
            found for ``port_name``.
        """
        for func_meta in self.function_meta.values():
            for input_name, input_meta in func_meta.get("inputs", {}).items():
                read_meta = input_meta.get("read")
                if not read_meta:
                    continue
                if isinstance(read_meta, dict):
                    read_func = None
                    for variant in (port_name, port_name.rstrip("s"), port_name + "s"):
                        if variant in read_meta:
                            read_func = read_meta[variant]
                            break
                    if read_func is not None:
                        suffix_val = input_meta.get("suffix")
                        suffix = (
                            suffix_val.get(port_name)
                            if isinstance(suffix_val, dict)
                            else suffix_val
                        )
                        return {
                            "read": read_func,
                            "suffix": suffix,
                            "accepted_ports": input_meta.get("accepted_ports", []),
                        }
                elif isinstance(read_meta, str):
                    candidates = [input_name, *(input_meta.get("accepted_ports") or [])]
                    if port_name in candidates:
                        return input_meta
        return None

    def func_parameters(self, function_name):
        """Get the parameters for a specific function from the project."""
        func_meta = self.get_function_meta(function_name)
        params = {
            pn: self.parameter(pn, function_name) for pn in func_meta["parameters"]
        }

        return params

    def get_func_from_param(self, parameter_name: str) -> list:
        """Get the function name(s) associated with a specific parameter
        name."""
        associated_functions = [
            func_name
            for func_name, func_meta in self.function_meta.items()
            if parameter_name in func_meta.get("parameters", {})
        ]
        return associated_functions

    def get_func_by_input(self, input_name: str) -> list:
        """Get the function name(s) associated with a specific input
        name."""
        input_name = "raw" if input_name in self.raw_types else input_name
        associated_functions = [
            func_name
            for func_name, func_meta in self.function_meta.items()
            if input_name in func_meta.get("inputs", {})
            or any(
                input_name in ip["accepted_ports"]
                for ip in func_meta.get("inputs", {}).values()
            )
        ]
        return associated_functions

    def get_func_by_output(self, output_name: str) -> list:
        """Get the function name(s) associated with a specific output
        name."""
        output_name = "raw" if output_name in self.raw_types else output_name
        associated_functions = [
            func_name
            for func_name, func_meta in self.function_meta.items()
            if output_name in func_meta.get("outputs", {})
            or any(
                output_name in op["accepted_ports"]
                for op in func_meta.get("outputs", {}).values()
            )
        ]
        return associated_functions

    ####################################################################################
    # Plugins
    ####################################################################################
    def load_plugin(self, plugin, plugin_name, plugin_meta):
        """Load the configuration file for a plugin."""
        config_path = plugin_meta.get("config_path")
        # config-path can already be the config-dict if suplied by load_plugin_code
        if isinstance(config_path, dict):
            functions = config_path
        elif isfile(config_path):
            functions = load_json(config_path, no_gui=False)
        else:
            raise ValueError(
                f"Invalid config_path for plugin '{plugin_name}': {config_path}. Must be a dict or a valid path to a JSON config file."
            )
        # add plugin-name to function metadata for later retrival
        for func, func_meta in functions.items():
            if not isinstance(func_meta, dict):
                raise TypeError(
                    f"Invalid metadata for function '{func}' in plugin '{plugin_name}'. Expected a dict, got {type(func_meta).__name__}."
                )
            self.set_dict_value("functions", func, plugin_name)
            func_meta["plugin"] = plugin_name
        # Populate plugin-meta
        self.set_dict_value("plugin_meta", plugin_name, plugin_meta)
        # Warn for duplicates, but let the newly loaded plugin's functions win
        duplicate_functions = [fn for fn in functions if fn in self.function_meta]
        if len(duplicate_functions) > 0:
            raise_user_attention(
                f"Duplicate function names found in plugin '{plugin_name}': {duplicate_functions}. The newly loaded versions will replace the existing ones.",
                "warning",
            )
        self.plugins[plugin_name] = plugin
        self.function_meta.update(functions)

    def load_plugin_module(self, plugin):
        plugin_name = getattr(plugin, "PLUGIN_NAME", None) or plugin.__name__
        config_path = getattr(plugin, "CONFIG_PATH", None)
        if config_path is None:
            raise ValueError(
                "CONFIG_PATH must be defined in __init__.py of the plugin!"
            )
        plugin_meta = {"config_path": config_path}
        script_path = getattr(plugin, "SCRIPT_PATH", None)
        if script_path is not None:
            plugin_meta["script_path"] = script_path
        plugin_github = getattr(plugin, "PLUGIN_GITHUB", None)
        if plugin_github is not None:
            plugin_meta["plugin_github"] = plugin_github
            plugin_meta["plugin_type"] = "github"
        else:
            plugin_meta["plugin_type"] = "module"
        self.load_plugin(plugin, plugin_name, plugin_meta)

    def _import_with_install_prompt(
        self, name: str, github: bool = False, plugin_url: str | None = None
    ) -> ModuleType | None:
        """Import a module, offering to install it first if it is missing."""
        if github:
            if plugin_url is None:
                raise ValueError("plugin_url must be given when github=True.")
            importer = partial(import_distribution, name)
            installer = partial(install_github_package, plugin_url)
            prompt_suffix = f" from '{plugin_url}'"
        else:
            importer = partial(import_module, name)
            installer = partial(install_pip_packages, [name])
            prompt_suffix = ""
        try:
            return importer()
        except ModuleNotFoundError:
            ans, cancel = question_yes_no(
                f"Module '{name}' not found. Do you want to install it{prompt_suffix}?"
            )
            if cancel or not ans:
                return None
            installer()
            try:
                return importer()
            except ModuleNotFoundError:
                raise_user_attention(
                    f"Failed to import module '{name}' after installation.",
                    message_type="info",
                )
                return None

    def load_plugin_module_name(self, plugin_name: str) -> None:
        plugin = self._import_with_install_prompt(plugin_name)
        if plugin is not None:
            self.load_plugin_module(plugin)

    def load_plugin_github(self, plugin_url: str) -> None:
        distribution_name = get_name_from_github(plugin_url)
        plugin = self._import_with_install_prompt(
            distribution_name, github=True, plugin_url=plugin_url
        )
        if plugin is not None:
            self.load_plugin_module(plugin)

    def load_plugin_path(self, config_path: str | Path):
        config_path = Path(config_path)
        path_was_missing = False
        if not config_path.is_file():
            path_was_missing = True
            raise_user_attention(
                f"Plugin config file '{config_path}' not found. Please select "
                "the new location.",
                message_type="info",
            )
            config_path = get_user_input(
                "Select a plugin configuration file to load.",
                input_type="file",
                file_filter="JSON files (*.json)",
            )  # type: ignore
            if config_path is None:
                return
            config_path = Path(config_path)
        pattern = r"([\w_]+)_config\.json$"
        match = re.search(pattern, str(config_path))
        if match:
            plugin_name = match.group(1)
        else:
            raise RuntimeError(
                "Plugin config file name must be in the format '<plugin_name>_config.json'"
            )
        folder_path = Path(config_path).parent
        script_path = Path(config_path).parent / f"{plugin_name}.py"
        if not isfile(script_path):
            raise RuntimeError(
                f"Expected script file '{script_path.name}' not found in {script_path.parent}. For just loading a plugin from a config-file, the script file is required to be in the same folder as the config-file and named like '<plugin_name>.py'."
            )
        plugin_meta = {
            "config_path": config_path,
            "script_path": script_path,
            "plugin_type": "path",
        }
        if path_was_missing:
            # Save the new device-specific path to settings so it is used
            # automatically on the next session without prompting again.
            plugin_config = self.settings.get("plugin_config", {})
            plugin_config[plugin_name] = {
                "config_path": config_path,
                "script_path": script_path,
            }
            self.settings.set("plugin_config", plugin_config)
        if str(folder_path) not in sys.path:
            sys.path.append(str(folder_path))
        plugin = import_module(plugin_name)
        self.load_plugin(plugin, plugin_name, plugin_meta)

    def load_plugin_code(self, code: str):
        # ToDo Next: Further work on plugin system and refactor analyze code from FunctionImporter into Controller for general purpose.
        pass

    def load_recent_plugins(self, plugin_name: str | None = None) -> None:
        """Load plugins registered in the project config.

        Parameters
        ----------
        plugin_name : str | None
            If given, only this specific plugin is loaded.  If ``None`` (the
            default), all non-disabled plugins in ``plugin_meta`` are loaded.
        """
        device_plugin_config = self.settings.get("plugin_config", {})
        disabled_plugins = set(self.settings.get("disabled_plugins", []))
        plugin_meta_all = self.get("plugin_meta", {})
        items = (
            {plugin_name: plugin_meta_all[plugin_name]}.items()
            if plugin_name is not None and plugin_name in plugin_meta_all
            else plugin_meta_all.items()
        )
        for pname, plugin_meta in items:
            if pname in disabled_plugins:
                logger.debug(f"Skipping disabled plugin '{pname}'.")
                continue
            plugin_type = plugin_meta.get("plugin_type")
            match plugin_type:
                case "path":
                    # Prefer device-specific path stored in settings over the
                    # shared config path (which may not be valid on this device).
                    device_override = device_plugin_config.get(pname, {})
                    config_path = device_override.get(
                        "config_path", plugin_meta["config_path"]
                    )
                    self.load_plugin_path(config_path)
                case "github":
                    self.load_plugin_github(plugin_meta["plugin_github"])
                case "module":
                    self.load_plugin_module_name(pname)
                case _:
                    logger.warning(
                        f"Unknown plugin type '{plugin_type}' for plugin '{pname}'. Skipping."
                    )

    def get_plugin_from_function(self, function_name: str) -> str:
        """Return the plugin path configured for a function."""
        function_meta = self.get_function_meta(function_name)
        plugin_name = function_meta.get("plugin")
        if not isinstance(plugin_name, str) or plugin_name.strip() == "":
            raise KeyError(
                f"Function '{function_name}' has no valid plugin configured."
            )
        return plugin_name

    def _unload_plugin_session(self, plugin_name: str) -> list[str]:
        """Remove a plugin and its functions from the current in-memory session.

        Removes the plugin from ``self.plugins``, clears the associated entries
        from ``self.function_meta``, and removes every matching
        :class:`~mne_nodes.gui.node.nodes.FunctionNode` from the node-viewer.

        Parameters
        ----------
        plugin_name : str
            Name of the plugin to unload.

        Returns
        -------
        list[str]
            Function names that were removed from ``function_meta``.
        """
        self.plugins.pop(plugin_name, None)
        functions_to_remove = [
            fn
            for fn, pm in self.function_meta.items()
            if pm.get("plugin") == plugin_name
        ]
        for fn in functions_to_remove:
            self.function_meta.pop(fn, None)

        # Remove matching nodes from the viewer if it is available
        if self.viewer is not None:
            nodes_to_remove = [
                node
                for node in list(self.viewer.nodes.values())
                if getattr(node, "name", None) in functions_to_remove
            ]
            for node in nodes_to_remove:
                self.viewer.remove_node(node, force=True)
            self.viewer.refresh_node_picker()

        return functions_to_remove

    def disable_plugin(self, plugin_name: str) -> None:
        """Unload a plugin from the current session and mark it as disabled.

        The plugin remains registered in the project config (``plugin_meta``) so
        that it can be re-enabled later.  The in-session unload removes its
        functions from ``function_meta`` and removes its nodes from the viewer.

        Parameters
        ----------
        plugin_name : str
            Name of the plugin to disable.
        """
        self._unload_plugin_session(plugin_name)
        disabled = set(self.settings.get("disabled_plugins", []))
        disabled.add(plugin_name)
        self.settings.set("disabled_plugins", list(disabled))

    def enable_plugin(self, plugin_name: str) -> None:
        """Re-enable a previously disabled plugin in device settings and reload it.

        Removes the plugin from the disabled list, loads it immediately in the
        current session via :meth:`load_recent_plugins`, and then tells the
        node-viewer to refresh the node picker so the newly available functions
        show up right away.

        Parameters
        ----------
        plugin_name : str
            Name of the plugin to re-enable.
        """
        disabled = set(self.settings.get("disabled_plugins", []))
        disabled.discard(plugin_name)
        self.settings.set("disabled_plugins", list(disabled))
        # Reload the plugin immediately in the current session
        self.load_recent_plugins(plugin_name)
        # Refresh the node picker in the viewer if available
        if self.viewer is not None:
            self.viewer.refresh_node_picker()

    def remove_plugin(self, plugin_name: str) -> None:
        """Unload a plugin and remove its registration from the project.

        Plugin files and installed distributions are intentionally left in
        place so the plugin can be registered again later.

        Parameters
        ----------
        plugin_name : str
            Name of the plugin to remove.
        """
        # Unload from current session (also removes viewer nodes)
        functions_to_remove = self._unload_plugin_session(plugin_name)

        # Remove from config
        plugin_meta_config = self.get("plugin_meta", {})
        plugin_meta_config.pop(plugin_name, None)
        self.set("plugin_meta", plugin_meta_config)
        functions_config = self.get("functions", {})
        for fn in functions_to_remove:
            functions_config.pop(fn, None)
        self.set("functions", functions_config)

        # Remove device-specific settings entry
        plugin_config = self.settings.get("plugin_config", {})
        plugin_config.pop(plugin_name, None)
        self.settings.set("plugin_config", plugin_config)
        disabled_plugins = set(self.settings.get("disabled_plugins", []))
        disabled_plugins.discard(plugin_name)
        self.settings.set("disabled_plugins", list(disabled_plugins))

    def reload_plugins(self, plugin_name: str | None = None) -> None:
        """Reload all plugins in the controller.

        This refreshes selected or all plugins by removing them from sys.modules
        and importing them again so source changes take effect.

        Parameters
        ----------
        plugin_name : str | None
            Provide a plugin_name (must be unique) to be reloaded. If None,
            all plugins are reloaded.

        Notes
        -----
        This updates the controller's plugins, but it does not update
        existing references to objects (e.g. functions) obtained before reload.
        Acquire fresh references after calling this.

        Examples
        --------
        >>> controller = Controller()
        >>> func = controller.plugins["plugin_name"].some_func
        >>> controller.reload_plugins()
        >>> new_func = controller.plugins["plugin_name"].some_func
        """

        if plugin_name is None:
            plugins_to_reload = self.plugins
        else:
            plugin = sys.modules[plugin_name]
            plugins_to_reload = {plugin_name: plugin}

        for loaded_plugin_name, plugin in plugins_to_reload.items():
            # Remove the plugin from sys.modules
            del sys.modules[loaded_plugin_name]

            # Clear bytecode cache if possible
            bytecode_file = cache_from_source(str(plugin.__file__))
            try:
                os.remove(bytecode_file)
            except OSError as e:
                logger.warning(f"Error clearing bytecode cache: {e}")

            # Import the plugin again
            reloaded_plugin = import_module(loaded_plugin_name)
            # Update the plugin in the controller
            self.plugins[loaded_plugin_name] = reloaded_plugin

    def get_function_meta(self, function_name: str) -> dict[str, Any]:
        """Get the metadata for a specific function."""
        function_meta = self.function_meta.get(function_name, None)
        if function_meta is None:
            match = re.match(r"([\w\.]+)-\d+", function_name)
            if match:
                function_meta = self.function_meta[match.group(1)]
            else:
                raise KeyError(
                    f"Function '{function_name}' not found in function meta."
                )

        return function_meta

    def get_functions_categorized(self) -> dict[str, list[str]]:
        """Get the functions categorized by their category and subcategory."""
        categorized = {}
        for func_name, func_meta in self.function_meta.items():
            category = func_meta.get("category", "Uncategorized")
            subcategory = func_meta.get("sub_category", None)
            if category not in categorized:
                categorized[category] = {}

            if subcategory is not None:
                # Add to subcategory dictionary
                if subcategory not in categorized[category]:
                    categorized[category][subcategory] = []
                categorized[category][subcategory].append(func_name)
            else:
                # Add to category's main list if it doesn't exist yet
                if "__main__" not in categorized[category]:
                    categorized[category]["__main__"] = []
                categorized[category]["__main__"].append(func_name)
        return categorized

    def get_parameter_meta(
        self, parameter_name: str, function_name: str
    ) -> dict[str, Any]:
        """Get the metadata for a specific parameter."""
        function_meta = self.get_function_meta(function_name)
        parameter_meta = function_meta["parameters"].get(parameter_name, None)
        if parameter_meta is None:
            raise KeyError(
                f"Parameter '{parameter_name}' not found in function '{function_name}' meta."
            )

        return parameter_meta

    def get_input_meta(self, function_name: str, input_name: str) -> dict[str, Any]:
        """Get the metadata for a specific data input/output."""
        function_meta = self.get_function_meta(function_name)
        input_meta = function_meta["inputs"].get(input_name, None)
        if input_meta is None:
            raise KeyError(
                f"Data '{input_name}' not found in function '{function_name}' meta."
            )

        return input_meta

    def get_output_meta(self, function_name: str, output_name: str) -> dict[str, Any]:
        """Get the metadata for a specific data output."""
        function_meta = self.get_function_meta(function_name)
        output_meta = function_meta["outputs"].get(output_name, None)
        if output_meta is None:
            raise KeyError(
                f"Data '{output_name}' not found in function '{function_name}' meta."
            )
        return output_meta

    @staticmethod
    def _get_func_start_end(function_name, plugin_code):
        tree = ast.parse(plugin_code)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == function_name:
                # lineno and end_lineno are 1-based
                start_line = node.lineno - 1
                end_line = (node.end_lineno or node.lineno) - 1

                return start_line, end_line
        logger.warning("Could not find function in module code.")

        return None, None

    def get_function_code(self, function_name: str):
        """Get the code for a specific function from the plugins."""
        plugin_name = self.get_plugin_from_function(function_name)
        plugin = self.plugins[plugin_name]
        function = getattr(plugin, function_name)
        if function is None:
            raise KeyError(
                f"Function '{function_name}' not found in plugin '{plugin_name}'."
            )
        plugin_code = getsource(plugin)
        func_code = getsource(function)
        start, end = self._get_func_start_end(function_name, plugin_code)

        return func_code, start, end

    ####################################################################################
    # config file management
    ####################################################################################

    def new_config(self, config_path: str | Path | None = None) -> Path | None:
        """Create a new configuration file and make it the active project config."""
        if config_path is None:
            config_path = get_user_input(
                "Select a location for the new configuration file.",
                input_type="file_new",
                file_filter="JSON files (*.json)",
                cancel_allowed=True,
            )
            if config_path is None:
                logger.warning("New configuration cancelled by user.")
                return None

        project_name = self.get("name", None)
        if not isinstance(project_name, str) or project_name.strip() == "":
            project_name = get_user_input(
                "Please enter a name for this project",
                input_type="string",
                cancel_allowed=False,
            )
            if project_name is None:
                raise RuntimeError("Project name initialization failed.")
            project_name = str(project_name)

        self._config = {"name": project_name, **deepcopy(default_config)}
        self._activate_config_path(config_path)
        self.flush()
        return self._config_path

    def load_config(self, config_path: str | Path | None = None) -> Path | None:
        """Load an existing configuration file into the active controller instance."""
        if config_path is None:
            config_path = get_user_input(
                "Please enter the path to an existing config-file",
                input_type="file",
                file_filter="JSON files (*.json)",
                cancel_allowed=True,
            )
            if config_path is None:
                logger.warning("Load configuration cancelled by user.")
                return None

        self.config_path = config_path
        return self._config_path

    def save_config(self) -> Path | None:
        """Write the in-memory configuration to the active config file."""
        if self._config_path is None:
            return self.save_config_as()
        self.flush()
        return self._config_path

    def save_config_as(self, export_path=None) -> Path | None:
        """Write the current configuration to a new config file and switch active file."""
        if export_path is None:
            export_path = get_user_input(
                "Select a location to save the configuration file.",
                input_type="file_new",
                file_filter="JSON files (*.json)",
                cancel_allowed=True,
            )
            if export_path is None:
                logger.warning("Save configuration cancelled by user.")
                return None

        self._activate_config_path(export_path)
        self.flush()
        return self._config_path

    def export_pipeline(self, export_path=None):
        """Backward-compatible alias for configuration save-as behavior."""
        return self.save_config_as(export_path)

    def start(self, node_sequence):
        # Generate code file
        code = CodeGenerator(self, node_sequence).code
        run_file_path = self.run_script_folder / f"{self.name}_pipeline.py"
        with open(run_file_path, "w") as file:
            file.write(code)
        logger.info(f"Pipeline code generated at {run_file_path}.\nStarting execution.")
        # Start process in Console-Dock (handle processes there)
        self.main_window.console_dock.start_process(
            sys.executable, [str(run_file_path)]
        )
