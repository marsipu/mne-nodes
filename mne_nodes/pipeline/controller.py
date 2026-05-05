"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import ast
import json
import logging
import os
import re
import sys
from copy import deepcopy
from importlib import import_module
from importlib.util import cache_from_source
from inspect import getsource
from os.path import isdir, isfile
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, Optional, Union

import mne
from filelock import FileLock, Timeout
from mne_bids import get_datatypes, get_entity_vals, BIDSPath, get_bids_path_from_fname

from mne_nodes import _widgets
from mne_nodes.core_functions import core_functions
from mne_nodes.gui.gui_utils import (
    get_user_input,
    raise_user_attention,
    ask_user_custom,
    ask_user,
)
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
        self.lock_timeout = 5  # seconds
        self.disk_interval = 1  # seconds
        self._last_load = 0
        self._local_set = False
        self.modules = {}
        self.function_meta = {}
        # raw datatypes
        self.raw_types = ["eeg", "meg", "ieeg"]
        # possible scopes for grouping and selection
        self.scopes = ["subject", "session", "run", "task", "custom"]
        self._process_count = 0
        # Initialize config_path here without prompting. Interactive setup is
        # handled explicitly via ensure_* methods after QApplication startup.
        config_path = config_path or self.settings.get("config_path", default=None)
        config_path = self._as_path(config_path)
        if config_path is not None and not config_path.is_file():
            logging.warning(f"Config file {config_path} does not exist!")
            config_path = None
        if config_path is not None:
            self.config_path = config_path
        # Add core functions to modules (until separated)
        self.add_module(Path(core_functions.__file__))
        # Initialize modules
        self.load_modules()

    ####################################################################################
    # Initialization and Properties
    ####################################################################################
    @property
    def config_path(self) -> Path | None:
        """Path to the config-file."""
        return self._config_path

    @config_path.setter
    def config_path(self, value):
        """Set the path to the config-file (respects interactive mode)."""
        # Check existence and prompt user for a new config-file if needed
        if value is None:
            ans = ask_user_custom(
                "Do you want to create a new config-file or use an existing one?",
                buttons=("Create new", "Use existing"),
                close_on_cancel=True,
            )
            if ans is None:  # user cancelled
                logging.info("User canceled, closing app.")
                sys.exit(0)
            elif ans:
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
                value = config_folder / f"{name}_config.json"
                with open(value, "w", encoding="utf-8") as file:
                    json.dump(config, file, indent=4, cls=TypedJSONEncoder)
                raise_user_attention(f"New configuration created at:\n{value}", "info")
            else:
                logging.info("Using existing config-file.")
                value = self._as_path(
                    get_user_input(
                        "Please enter the path to an exisiting config-file",
                        input_type="file",
                        file_filter="JSON files (*.json)",
                        exit_on_cancel=True,
                    )
                )
                raise_user_attention(
                    f"Configuration sucessfully loaded from:\n{value}", "info"
                )
        config_path = self._as_path(value)
        if config_path is None:
            raise RuntimeError("Config path initialization failed.")
        # Set the path and initialize the lock
        self._config_path = config_path
        self._config_lock = FileLock(self._config_path.with_suffix(".lock"))
        self.settings.set("config_path", self._config_path)
        # Load the config immediately
        if self._config_path.is_file():
            self.load()
        else:
            self.flush()

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

    def _setting_path(self, key: str) -> Path | None:
        path_value = self._as_path(self.settings.get(key, None))
        if path_value is not None and path_value.is_dir():
            return path_value
        return None

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

    def ensure_config_path(self, interactive: bool = True) -> Path:
        if self._config_path is not None:
            return self._config_path
        if not interactive:
            raise RuntimeError(
                "Config path is not initialized. Call ensure_config_path() first."
            )
        self.config_path = None
        if self._config_path is None:
            raise RuntimeError("Config path initialization failed.")
        return self._config_path

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
        name = get_user_input(
            "Please enter a name for this project", "string", cancel_allowed=False
        )
        if name is None:
            raise RuntimeError("Project name initialization failed.")
        coerced_name = str(name)
        self.set("name", coerced_name)
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
        selected_path = self._as_path(
            get_user_input(
                "Please enter the path to the FreeSurfer subjects directory",
                "folder",
                cancel_allowed=False,
            )
        )
        if selected_path is None:
            raise RuntimeError("FreeSurfer subjects directory initialization failed.")
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
    def bids_root(self) -> Path | None:
        """Configured BIDS root directory, if available."""
        return self._setting_path("bids_root")

    @bids_root.setter
    def bids_root(self, value: os.PathLike) -> None:
        if not isdir(value):
            raise ValueError(f"Path {value} does not exist!")
        ans = ask_user(
            "When you change the BIDS-root, all selections and custom groups will be lost. Do you want to proceed?"
        )
        if ans:
            # Clear selected inputs and custom groups
            self.get("selected_inputs").clear()
            self.get("custom_groups").clear()
            # Update input widget
            self.viewer.input_node.update_widgets()
            self.settings.set("bids_root", value)

    @property
    def deriv_root(self) -> Path | None:
        """Configured derivatives root directory, if available."""
        return self._setting_path("deriv_root")

    @deriv_root.setter
    def deriv_root(self, value: str | Path) -> None:
        if not isdir(value):
            raise ValueError(f"Path {value} does not exist!")
        self.settings.set("deriv_root", value)

    @property
    def subjects_dir(self) -> Path | None:
        """Configured FreeSurfer subjects directory, if available."""
        if is_test():
            subjects_dir = self.settings.get("subjects_dir", None)
        else:
            subjects_dir = mne.get_config("SUBJECTS_DIR", None)
        subjects_dir = self._as_path(subjects_dir)
        if subjects_dir is not None and subjects_dir.is_dir():
            return subjects_dir
        return None

    @subjects_dir.setter
    def subjects_dir(self, value):
        if value is not None:
            if not isdir(value):
                raise ValueError(f"Path {value} does not exist!")
            if is_test():
                self.settings.set("subjects_dir", value)
            else:
                mne.set_config("SUBJECTS_DIR", value)

    @property
    def plot_root(self) -> Path | None:
        """Configured plot output directory, if available."""
        return self._setting_path("plot_root")

    @plot_root.setter
    def plot_root(self, value):
        if value is not None:
            if not isdir(value):
                raise ValueError(f"Path {value} does not exist!")
            self.settings.set("plot_root", value)

    @property
    def plot_path(self) -> Path:
        """Path to the plot directory for the current project."""
        plot_root = self.ensure_plot_root(interactive=False)
        name = self.ensure_name(interactive=False)
        plot_path = plot_root / name
        if not isdir(plot_path):
            plot_path.mkdir(parents=True, exist_ok=True)
        return plot_path

    @property
    def name(self) -> str | None:
        return self.get("name", None)

    @name.setter
    def name(self, new_name):
        old_name = self.get("name")
        if old_name != new_name and self._config_path is not None:
            # Rename the config file if the name changes
            old_path = self._config_path
            new_path = self._config_path.parent / f"{new_name}_config.json"
            os.rename(old_path, new_path)
            self._config_path = new_path
        self.set("name", new_name)

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
                    for bp in BIDSPath(**{group_by: v, "root": self.bids_root}).match()
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
        if parameter_name not in parameters.get(function_name, {}):
            logging.warning(
                f"Parameter '{parameter_name}' not found in project for function '{function_name}'. Setting default value."
            )
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
    def _load_module_config(self, module_name, module_path):
        """Load the configuration file for a module from the package path."""
        config_file_path = Path(module_path).parent / f"{module_name}_config.json"
        if not isfile(config_file_path):
            raise RuntimeError(
                f"Config file for {module_name} not found at {config_file_path}."
            )
        # load function-config
        with open(config_file_path) as file:
            config = json.load(file, object_hook=type_json_hook)["functions"]
        # Add module-names to function-metas to allow identification
        for func_dict in config.values():
            func_dict["module"] = module_name
        self.function_meta.update(config)

    def _import_module(self, module_name, module_path):
        """Import a module from the given package path."""
        pkg_path = Path(module_path).parent
        # Add the package path to sys.path if not already present
        if pkg_path not in sys.path:
            sys.path.insert(0, str(pkg_path))
        pkg_name = pkg_path.name
        # Import the module from the package
        try:
            module = import_module(module_name, package=pkg_name)
        except ModuleNotFoundError:
            logging.error(f"Module {module_name} not found in {pkg_path}].")
        else:
            self.modules[module_name] = module
        # Load the config file for the basic module
        self._load_module_config(module_name, module_path)

    def load_modules(self) -> None:
        """Load custom modules from their config files."""
        modules = self.settings.get("module_meta")
        for module_name, module_config in modules.items():
            module_path = module_config["path"]
            if not isfile(module_path):
                module_path = get_user_input(
                    f"{module_path} was not found! Please supply the path to {Path(module_path).name}.",
                    input_type="file",
                    file_filter="Python files (*.py)",
                )
            self._import_module(module_name, module_path)

    def add_module(self, module_path: os.PathLike) -> None:
        """Add a module to the controller from a config file or a script-file."""
        if not isfile(module_path):
            raise FileNotFoundError(f"Module file {module_path} not found.")
        module_name = Path(module_path).stem
        config_path = Path(module_path).parent / f"{module_name}_config.json"
        if not isfile(config_path):
            raise FileNotFoundError(f"Config file {config_path} not found.")
        # Load module-config
        with open(config_path) as file:
            config = json.load(file, object_hook=type_json_hook)["module"]
        # Add local path to module-meta to find it on this device (path is not stored in the json-config, since the module should be able to be copied easily between devices)
        config["path"] = module_path
        # Save module-meta to settings
        module_meta = self.settings.get("module_meta", {})
        module_meta[module_name] = config
        self.settings.set("module_meta", module_meta)
        # Import module
        self._import_module(module_name, module_path)

    def reload_modules(self, module_name: Optional[str] = None) -> None:
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
        This updates the controller's module objects, but it does not update
        existing references to objects (e.g. functions) obtained before reload.
        Acquire fresh references after calling this.

        Examples
        --------
        >>> controller = Controller()
        >>> func = controller.modules["module_name"].some_func
        >>> controller.reload_modules()
        >>> new_func = controller.modules["module_name"].some_func
        """

        if module_name is None:
            modules = self.modules
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
            self.modules[module_name] = new_module

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
        module = self.modules[module_name]
        function = getattr(module, function_name)
        if function is None:
            raise KeyError(
                f"Function '{function_name}' not found in module '{module_name}'."
            )
        module_code = getsource(module)
        func_code = getsource(function)
        start, end = self._get_func_start_end(function_name, module_code)

        return func_code, start, end

    def get_datatypes(self):
        # ToDo: Implement data-types other than raw
        bids_root = self.ensure_bids_root(interactive=False)
        excluded_datatypes = ["anat", "func"]
        return [dt for dt in get_datatypes(bids_root) if dt not in excluded_datatypes]

    @staticmethod
    def tab(num_tabs=1, tab_size=4):
        """Return a string of tabs for indentation."""
        return " " * (num_tabs * tab_size)

    def _build_header(self, functions):
        code = (
            "# This code was generated by mne-nodes\n\n"
            "import os\n"
            "import traceback\n"
            "import logging\n"
            "from tqdm import tqdm\n"
            "from rich.pretty import pprint\n"
            "import mne\n"
            "from mne_bids import BIDSPath, read_raw_bids, get_datatypes, get_bids_path_from_fname\n"
            "import mne_nodes\n"
            "from mne_nodes.pipeline.controller import Controller\n"
            "# Activate matplotlibs interactive mode\n"
            "import matplotlib.pyplot as plt\n"
            "plt.ion()\n"
            "# Disable gui-mode\n"
            "mne_nodes.gui_mode = False\n\n"
            "# Load controller\n"
            f"ct = Controller(config_path='{self.ensure_config_path(interactive=False).as_posix()}')\n\n"
            "# Inject modules into global namespace\n"
            "globals().update(ct.modules)\n"
            "# Import modules\n"
        )
        # Add module imports
        modules = set(functions.values())
        for module in modules:
            code += f"from {module} import {', '.join([f for f, m in functions.items() if m == module])}\n"
        return code

    @staticmethod
    def _indent(code, num_tabs=1):
        """Indent a code string by a given number of tabs."""
        indent_str = Controller.tab(num_tabs)
        # If line empty, don't indent
        indented_code = "\n".join(
            indent_str + line for line in code.splitlines() if line != ""
        )
        indented_code += "\n"
        return indented_code

    def convert_to_code(self, node_sequence):
        """Convert a list of instructions to a Python code string."""
        # start code with header and imports
        functions = {
            n["name"]: self.get_function_meta(n["name"])["module"]
            for n in node_sequence
            if n["class"] == "FunctionNode"
        }
        code = self._build_header(functions)
        code += "\n# Execute pipeline\n"
        # Get available datatypes
        data_types = self.get_datatypes()
        # Ordering targets (files first)
        targets = {t: [] for t in ["file", "group"]}
        for n in node_sequence:
            if n["class"] == "FunctionNode":
                func_meta = self.get_function_meta(n["name"])
                target = func_meta["target"]
                if target not in targets:
                    logging.warning(
                        f"Target '{target}' not recognized. Step {n['name']} will be ignored in code generation."
                    )
                    continue
                targets[target].append(n)
        # Iterate nodes
        for target, nodes in targets.items():
            if len(nodes) == 0:
                continue
            code += f"# Target: {target}\n"
            loaded_data = []
            for selection_type in [
                key
                for key, items in self.get("selected_inputs").items()
                if len(items) > 0
            ]:
                if (selection_type in self.scopes and target == "file") or (
                    selection_type in data_types and target == "group"
                ):
                    continue
                code += f"# Selection-Type: {selection_type}\n"
                if target == "group":
                    code += f"group = ct.get_group_by('{selection_type}')\n"
                code += f"for item in ct.get('selected_inputs')['{selection_type}']:\n"
                # Prepare bids-paths
                if target == "file" and selection_type in data_types:
                    code += self._indent("bp = get_bids_path_from_fname(item)\n", 1)
                elif target == "group":
                    # For group-data, load and return generators of the group-members
                    code += self._indent("members = group[item]\n", 1)
                for n in nodes:
                    name = n["name"]
                    for ip in [i for i in n["inputs"] if i not in loaded_data]:
                        # Load selected data-types (if not already loaded)
                        if ip == "raw":
                            # Load raw from original bids-dataset
                            if target == "file":
                                code += self._indent(
                                    "bp_raw = bp.copy().update(root=ct.bids_root)\n", 1
                                )
                                code += self._indent("raw = read_raw_bids(bp_raw)\n", 1)
                            else:
                                code += self._indent(
                                    "raw = (read_raw_bids(rp) for rp in members)\n", 1
                                )
                            loaded_data.append("raw")
                        else:
                            # Load data from derivatives
                            input_meta = self.get_input_meta(
                                function_name=name, input_name=ip
                            )
                            load_func = input_meta.get("load", None)
                            if load_func is not None:
                                suffix = input_meta.get("suffix") or ip
                                # Load data from storage
                                code += self._indent(f"# Load {ip}", 1)
                                code += self._indent(
                                    f"load_kwargs = ct.get_input_meta('{name}', '{ip}').get('load_kwargs', {{}})\n",
                                    1,
                                )
                                if target == "file":
                                    code += self._indent(
                                        f"data_path = bp.copy().update(suffix='{suffix}', root=ct.deriv_root, check=False).fpath\n",
                                        1,
                                    )
                                    # This assumes, that the file-path is always the first argument in a load-function
                                    code += self._indent(
                                        f"{ip} = {load_func}(data_path, **load_kwargs)\n",
                                        1,
                                    )
                                else:
                                    code += self._indent(
                                        f"{ip} = ({load_func}(dp, **load_kwargs) for dp in [bp.copy().update(suffix='{suffix}', root=ct.deriv_root, check=False).fpath for bp in members])\n",
                                        1,
                                    )
                            loaded_data.append(ip)
                    code += self._indent(f"# Execute function {name}\n", 1)
                    code += self._indent(
                        f"print(f'Executing {name} for {{item}} with the following parameters:')\n",
                        1,
                    )
                    code += self._indent(
                        f"func_params = ct.func_parameters('{name}')", 1
                    )
                    code += self._indent("pprint(func_params)\n", 1)
                    outputs = ", ".join([op for op in n["outputs"]])
                    loaded_data += n["outputs"]
                    inputs = ", ".join([f"{ip}={ip}" for ip in n["inputs"]])
                    func_line = ""
                    if outputs:
                        func_line += f"{outputs} = "
                    func_line += f"{name}("
                    if inputs:
                        func_line += f"{inputs}, **func_params)"
                    else:
                        func_line += "**func_params)"
                    code += self._indent(func_line, 1)
                    # Save outputs (if enabled)
                    if n["checked"]:
                        for op in n["outputs"]:
                            output_meta = self.get_output_meta(
                                function_name=name, output_name=op
                            )
                            save_func = output_meta.get("save", None)
                            if save_func is not None:
                                suffix = output_meta.get("suffix") or op
                                # Save data to storage
                                code += self._indent(f"# Save {op}\n", 1)
                                if target == "file":
                                    code += self._indent(
                                        f"data_path = bp.copy().update(suffix='{suffix}', root=ct.deriv_root, check=False).fpath\n",
                                        1,
                                    )
                                else:
                                    code += self._indent(
                                        f"data_path = members[0].copy().update(subject='average', suffix='{suffix}', root=ct.deriv_root, check=False)\n"
                                        "data_path.mkdir(exist_ok=True)\n",
                                        1,
                                    )
                                code += self._indent(
                                    f"save_kwargs = ct.get_output_meta(function_name='{name}', output_name='{op}').get('save_kwargs', {{}})\n",
                                    1,
                                )
                                if save_func.startswith("."):
                                    code += self._indent(
                                        f"{op}{save_func}(data_path, **save_kwargs)\n",
                                        1,
                                    )
                                else:
                                    # This assumes, that the file-path is always the first argument in a save-function
                                    code += self._indent(
                                        f"{save_func}(data_path, {op}, **save_kwargs)\n",
                                        1,
                                    )

        code += "# Keep matplotlib plots open\nplt.ioff()\nplt.show(block=True)\n"
        code += "import time\ntime.sleep(100)"

        return code

    def start(self, node_sequence):
        # Generate code file
        code = self.convert_to_code(node_sequence)
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
