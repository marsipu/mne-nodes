"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import ast
from importlib.metadata import entry_points
import json
import logging
import os
import re
import sys
from copy import deepcopy
from importlib import import_module
from importlib.util import cache_from_source
from inspect import getsource
from os.path import isdir
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Dict, List, Optional, Union

import mne
from filelock import FileLock, Timeout
from mne_bids import get_datatypes, get_entity_vals, BIDSPath, get_bids_path_from_fname

from mne_nodes import _widgets
from mne_nodes.gui.gui_utils import (
    get_user_input,
    install_pip_packages,
    raise_user_attention,
    ask_user_custom,
    ask_user,
)
from mne_nodes.pipeline.code_generation import CodeGenerator
from mne_nodes.pipeline.io import TypedJSONEncoder, type_json_hook
from mne_nodes.pipeline.pipeline_utils import is_test
from mne_nodes.pipeline.settings import Settings

default_config = {
    # BIDS
    "selected_inputs": {},  # BIDS entity values as keys for lists
    "group_by": "subject",
    "custom_groups": {},
    # Legacy entries from old Project class
    "all_meeg": [],
    "all_fsmri": [],
    "all_erm": [],
    "all_groups": {},
    "sel_meeg": [],
    "sel_fsmri": [],
    "bad_channels": {},
    "event_ids": {},
    "selected_event_ids": {},
    "ica_exclude": {},
    "add_kwargs": {},
    # Parameters
    "parameters": {},
    # Application Configuration
    "show_plots": True,
    "save_plots": True,
    "shutdown": False,
    "img_format": ".png",
    "dpi": 150,
    "overwrite": False,
    "use_plot_manager": False,
    "log_level": 20,
    "education": 0,
    "app_font": "Calibri",
    "app_font_size": 10,
    "app_style": "fusion",
    "app_theme": "auto",
    "padding": 20,
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
        self,
        config_path: Optional[Union[str, Path]] = None,
        settings: Optional[Settings] = None,
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
        self.disk_interval = 1  # seconds
        # raw datatypes
        self.raw_types = ["eeg", "meg", "ieeg"]
        # possible scopes for grouping and selection
        self.scopes = ["subject", "session", "run", "task", "custom"]
        self._process_count = 0
        # Initialize config_path here without prompting. Interactive setup is
        # handled explicitly via ensure_* methods after QApplication startup.
        self._initialize_startup_config_path(config_path)
        # Initialize plugins
        self.load_plugins()

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
        logging.warning(f"Config file {startup_path} does not exist!")
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
            logging.info("User canceled, closing app.")
            sys.exit(0)
        if ans:
            logging.info("Creating new config-file.")
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
            raise_user_attention(
                f"New configuration created at:\n{config_path}", "info"
            )
            return config_path

        logging.info("Using existing config-file.")
        config_path = self._as_path(
            get_user_input(
                "Please enter the path to an exisiting config-file",
                input_type="file",
                file_filter="JSON files (*.json)",
                exit_on_cancel=True,
            )
        )
        if config_path is None:
            raise RuntimeError("Config path initialization failed.")
        raise_user_attention(
            f"Configuration sucessfully loaded from:\n{config_path}", "info"
        )
        return config_path

    def _apply_config_path(self, config_path: Path) -> None:
        self._config_path = config_path
        self._config_lock = FileLock(self._config_path.with_suffix(".lock"))
        self.settings.set("config_path", self._config_path)
        # Load the config immediately
        if self._config_path.is_file():
            self.load()
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
            logging.warning(missing_message.format(path=configured_path))
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
            logging.warning(missing_message.format(path=configured_path))
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

        ans = ask_user(
            "When you change the BIDS-root, all selections and custom groups will be lost. Do you want to proceed?"
        )
        if not ans:
            if previous_root is not None:
                self.settings.set("bids_root", previous_root)
            return

        # Clear selected inputs and custom groups
        self.get("selected_inputs").clear()
        self.get("custom_groups").clear()
        # Update input widget when viewer is available.
        try:
            self.viewer.input_node.update_widgets()
        except RuntimeError:
            pass

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

    def _load_config(self):
        """Load the configuration from the config-file if necessary."""
        config_path = self.ensure_config_path(interactive=False)
        try:
            with open(config_path) as file:
                config = json.load(file, object_hook=type_json_hook)
        except (
            OSError,
            json.JSONDecodeError,
            UnicodeDecodeError,
            FileNotFoundError,
        ) as err:
            logging.warning(
                f"Loading config from {config_path} failed with:\n{err}\nUsing defaults."
            )
            config = deepcopy(default_config)

        return config

    def _save_config(self, config) -> None:
        config_path = self.ensure_config_path(interactive=False)
        with open(config_path, "w") as file:
            json.dump(config, file, indent=4, cls=TypedJSONEncoder)

    def load(self):
        """Force loading the config from disk."""
        if self._config_path is None:
            logging.debug("Config path is not set. Keeping in-memory configuration.")
            return
        try:
            with self.config_lock:
                self._config = self._load_config()

        except Timeout:
            logging.warning(
                f"Could not acquire lock for settings after {self.lock_timeout} seconds."
            )

    def flush(self):
        """Force writing the current config to disk."""
        if self._config_path is None:
            logging.debug("Config path is not set. Skipping config flush.")
            return
        try:
            with self.config_lock:
                self._save_config(self._config)
        except Timeout:
            logging.error(
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

    def set(self, key, value) -> None:
        """Set a specific key in the config-file."""
        self._config[key] = value
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

    @property
    def run_script_folder(self):
        """Path to the local config folder."""
        local_config_path = Path.home() / ".mne-nodes"
        local_config_path.mkdir(parents=True, exist_ok=True)

        return local_config_path

    @property
    def viewer(self):
        """Get the viewer object from the _widgets dictionary."""
        viewer = _widgets.get("viewer", None)
        if viewer is None:
            raise RuntimeError(
                "Viewer is not initialized. Please initialize the viewer first."
            )
        return viewer

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
    def get_dataset_name(self) -> str | None:
        bids_root = self.ensure_bids_root(interactive=False)
        dataset_file = bids_root / "dataset_description.json"
        if not dataset_file.is_file():
            logging.warning(f"Dataset description file not found at {dataset_file}.")
            return None
        else:
            with open(dataset_file) as file:
                dataset_description = json.load(file)
            return dataset_description["Name"]

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

    def check_subject(self, subject):
        # ToDo next: get fsmri either by subject-name or by custom association
        fsmri_subjects = (
            os.listdir(self.subjects_dir) if self.subjects_dir is not None else []
        )
        result = subject in fsmri_subjects
        if not result:
            logging.warning(
                f"Subject {subject} not found in FreeSurfer subjects directory!"
            )
            return None
        return subject

    def get_datatypes(self):
        # ToDo: Implement data-types other than raw
        bids_root = self.ensure_bids_root(interactive=False)
        excluded_datatypes = ["anat", "func"]
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
            # logging.debug(
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

    def func_parameters(self, function_name):
        """Get the parameters for a specific function from the project."""
        func_meta = self.get_function_meta(function_name)
        params = {
            pn: self.parameter(pn, function_name) for pn in func_meta["parameters"]
        }

        return params

    def get_func_from_param(self, parameter_name: str) -> list[str] | str | None:
        """Get the function name(s) associated with a specific parameter
        name."""
        function_meta = self.function_meta
        associated_functions = [
            func_name
            for func_name, func_meta in function_meta.items()
            if parameter_name in func_meta.get("parameters", {})
        ]
        if not associated_functions:
            return None
        elif len(associated_functions) == 1:
            return associated_functions[0]
        else:
            return associated_functions

    ####################################################################################
    # Modules
    ####################################################################################
    def load_module_config(self, module):
        """Load the configuration file for a module"""
        config_path = getattr(module, "CONFIG_PATH", None)
        if config_path is not None:
            with open(config_path) as file:
                config = json.load(file, object_hook=type_json_hook)
            # Warn for duplicates
            duplicate_functions = [fn for fn in config if fn in self.function_meta]
            if len(duplicate_functions) > 0:
                raise_user_attention(
                    f"Duplicate function names found in module '{module.__name__}': {duplicate_functions}. Please rename those functions, they will not be imported until then",
                    "warning",
                )
                for df in duplicate_functions:
                    del config[df]
            self.function_meta.update(config)

    def load_plugins(self):
        for entry_point in [
            ep
            for ep in entry_points(group="mne_nodes.plugins")
            if ep.name not in self.plugins
        ]:
            logging.info(f"Loading {entry_point.name}")
            module = entry_point.load()
            self.load_module_config(module)
            self.plugins[entry_point.name] = module
        return self.plugins

    def reload_plugins(self, module_name: Optional[str] = None) -> None:
        """Reload all modules in the controller.

        This refreshes selected or all modules by removing them from sys.modules
        and importing them again so source changes take effect.

        Parameters
        ----------
        module_name : str | None
            Provide a module_name (must be unique) to be reloaded. If None,
            all modules are reloaded.

        Notes
        -----
        This updates the controller's plugins, but it does not update
        existing references to objects (e.g. functions) obtained before reload.
        Acquire fresh references after calling this.

        Examples
        --------
        >>> controller = Controller()
        >>> func = controller.plugins["module_name"].some_func
        >>> controller.reload_modules()
        >>> new_func = controller.plugins["module_name"].some_func
        """

        if module_name is None:
            modules = self.plugins
        else:
            module = sys.modules[module_name]
            modules = {module_name: module}

        for module_name, module in modules.items():
            # Remove the module from sys.modules
            del sys.modules[module_name]

            # Clear bytecode cache if possible
            bytecode_file = cache_from_source(str(module.__file__))
            try:
                os.remove(bytecode_file)
            except Exception as e:
                logging.warning(f"Error clearing bytecode cache: {e}")

            # Import the module again
            new_module = import_module(module_name)
            # Update the module in the controller
            self.plugins[module_name] = new_module

    def get_function_meta(self, function_name: str) -> Dict[str, Any]:
        """Get the metadata for a specific function."""
        function_meta = self.function_meta.get(function_name, None)
        if function_meta is None:
            match = re.match(r"([\w]+)-\d+", function_name)
            if match:
                function_meta = self.function_meta[match.group(1)]
            else:
                raise KeyError(
                    f"Function '{function_name}' not found in function meta."
                )

        return function_meta

    def get_functions_categorized(self) -> Dict[str, List[str]]:
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
    ) -> Dict[str, Any]:
        """Get the metadata for a specific parameter."""
        function_meta = self.get_function_meta(function_name)
        parameter_meta = function_meta["parameters"].get(parameter_name, None)
        if parameter_meta is None:
            raise KeyError(
                f"Parameter '{parameter_name}' not found in function '{function_name}' meta."
            )

        return parameter_meta

    def get_input_meta(self, function_name: str, input_name: str) -> Dict[str, Any]:
        """Get the metadata for a specific data input/output."""
        function_meta = self.get_function_meta(function_name)
        input_meta = function_meta["inputs"].get(input_name, None)
        if input_meta is None:
            raise KeyError(
                f"Data '{input_name}' not found in function '{function_name}' meta."
            )

        return input_meta

    def get_output_meta(self, function_name: str, output_name: str) -> Dict[str, Any]:
        """Get the metadata for a specific data output."""
        function_meta = self.get_function_meta(function_name)
        output_meta = function_meta["outputs"].get(output_name, None)
        if output_meta is None:
            raise KeyError(
                f"Data '{output_name}' not found in function '{function_name}' meta."
            )
        return output_meta

    @staticmethod
    def _get_func_start_end(function_name, module_code):
        tree = ast.parse(module_code)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == function_name:
                # lineno and end_lineno are 1-based
                start_line = node.lineno - 1
                end_line = (node.end_lineno or node.lineno) - 1

                return start_line, end_line
        logging.warning("Could not find function in module code.")

        return None, None

    def get_function_code(self, function_name: str):
        """Get the code for a specific function from the modules."""
        module_name = self.get_function_meta(function_name)["module"]
        module = self.plugins[module_name]
        function = getattr(module, function_name)
        if function is None:
            raise KeyError(
                f"Function '{function_name}' not found in module '{module_name}'."
            )
        module_code = getsource(module)
        func_code = getsource(function)
        start, end = self._get_func_start_end(function_name, module_code)

        return func_code, start, end

    ####################################################################################
    # Pipeline
    ####################################################################################
    def import_pipeline(self, import_path):
        with open(import_path) as file:
            pipeline_dict = json.load(file, object_hook=type_json_hook)
        # Import parameters
        self.set("parameters", pipeline_dict.get("parameters", {}))
        # import modules or install them if they have not been imported yet
        missing_plugins = [
            plugin
            for plugin in pipeline_dict.get("plugins", [])
            if plugin not in self.plugins
        ]
        if len(missing_plugins) > 0:
            logging.warning(
                f"Missing plugins found for this pipeline: {missing_plugins}. Attempting to install them."
            )
            install_pip_packages(missing_plugins, self.main_window)
            self.load_plugins()

        # import pipeline structure to viewer
        self.viewer.from_dict(pipeline_dict["nodes"])
        logging.info(f"Pipeline imported from {import_path}.")

    def import_pipeline_user_prompt(self):
        import_path = get_user_input(
            "Select a pipeline configuration file to import.",
            input_type="file",
            file_filter="JSON files (*.json)",
        )
        if import_path is None:
            logging.warning("Pipeline import cancelled by user.")
            return
        self.import_pipeline(import_path)

    def get_used_plugins(self):
        """Get all used plugins from the current function-nodes in the viewer."""
        plugins = set()
        for func_name in self.viewer.get_unique_functions():
            func_meta = self.get_function_meta(func_name)
            plugins.add(func_meta["module"])
        return plugins

    def export_pipeline(self, export_path):
        pipeline_dict = {
            "nodes": self.viewer.to_dict(),
            "plugins": self.get_used_plugins(),
            "parameters": self.get("parameters", {}),
        }
        with open(export_path, "w") as file:
            json.dump(pipeline_dict, file, indent=4, cls=TypedJSONEncoder)

    def export_pipeline_user_prompt(self):
        export_path = get_user_input(
            "Select a location to save the pipeline configuration.",
            input_type="file_new",
            file_filter="JSON files (*.json)",
        )
        if export_path is None:
            logging.warning("Pipeline export cancelled by user.")
            return
        self.export_pipeline(export_path)

    def start(self, node_sequence):
        # Generate code file
        code = CodeGenerator(self, node_sequence).code
        run_file_path = self.run_script_folder / f"{self.name}_pipeline.py"
        with open(run_file_path, "w") as file:
            file.write(code)
        logging.info(
            f"Pipeline code generated at {run_file_path}.\nStarting execution."
        )
        # Start process in Console-Dock (handle processes there)
        self.main_window.console_dock.start_process(
            sys.executable, [str(run_file_path)]
        )
