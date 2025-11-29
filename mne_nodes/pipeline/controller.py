"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import ast
import json
import logging
import os
import shutil
import sys
from copy import deepcopy
from importlib import import_module
from importlib.util import cache_from_source
from inspect import getsource
from os.path import isdir, join, isfile
from pathlib import Path
from types import NoneType
from typing import Any, Dict, Optional, Union

import mne
from filelock import FileLock, Timeout
from mne_nodes import _widgets
from mne_nodes.basic_operations import basic_operations
from mne_nodes.basic_plot import basic_plot
from mne_nodes.gui.gui_utils import get_user_input, ask_user, raise_user_attention
from mne_nodes.pipeline.execution import Process
from mne_nodes.pipeline.io import TypedJSONEncoder, type_json_hook
from mne_nodes.pipeline.pipeline_utils import is_test
from mne_nodes.pipeline.settings import Settings

default_config = {
    "plot_files": {},
    "input_types": {
        "raw": {"alias": "MEG/EEG", "import": "import_raw"},
        "fsmri": {"alias": "Freesurfer MRI", "import": "import_fsmri"},
    },
    "data_types": ["raw", "fsmri", "plot"],
    "inputs": {"raw": {"All": []}, "fsmri": {"All": []}},
    "input_mapping": {"fsmri": {}, "erm": {}},
    "selected_inputs": [],
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
    "selected_modules": ["basic_operations", "basic_plot"],
    "p_preset": "Default",
    "parameters": {"Default": {}},
    "module_meta": {},
    "function_metas": {},
    "parameter_metas": {},
    "add_kwargs": {},
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
    "tab": "    ",
    "node_config": {"nodes": {}, "connections": {}},
}


class Controller:
    """New controller, that combines the former old controller and project
    class and loads a controller for each "project".

    The home-path structure should no longer be as rigid as before, just specifying the
    path to meeg- and fsmri-data. For each controller, there is a config-file stored,
    where paths to the meeg-data, the freesurfer-dir and the custom-packages are stored.

    It is possible to get config values by accessing them as attributes of the
    controller, e.g., controller.data_path. Importantly, setting attributes directly
    works while setting values inside of containers like controller.inputs doesn't work::
        controller.data_path = new_path  # works
        controller.inputs['raw']['subject1'] = new_value  # doesn't work

    Parameters
    ----------
    config_path : str or Path, optional
        Path to the config-file.
    initialize_paths : bool, keyword-only, default False
        If True, eagerly access path properties (may trigger user prompts).
        Default False so that a Controller can be created safely in a
        headless / non-QApplication context.
    settings : Settings, optional
        Settings object to use for device-dependent settings.
    """

    def __init__(
        self,
        config_path: Optional[Union[str, Path]] = None,
        initialize_paths: bool = False,
        settings: Optional[Settings] = None,
    ):
        # The device dependent settings
        self.settings = settings or Settings()
        self._config_path = None
        self._config_lock = None
        self.lock_timeout = 5  # seconds
        self.modules = {}
        self._process_count = 0
        self.config_path = config_path or self.settings.get("config_path", default=None)
        # Check existence of data_path (optional) only if requested
        if initialize_paths:
            try:
                _ = self.data_path  # may trigger lazy initialization
            except Exception as err:  # noqa: BLE001
                logging.debug("Deferring data_path initialization: %s", err)
        # Initialize modules
        # Legacy: Add basic modules until separated
        module_meta = self.get("module_meta")
        module_meta["basic_operations"] = {
            "module": Path(basic_operations.__file__),
            "config": Path(basic_operations.__file__).with_name(
                "basic_operations_config.json"
            ),
        }
        module_meta["basic_plot"] = {
            "module": Path(basic_plot.__file__),
            "config": Path(basic_plot.__file__).with_name("basic_plot_config.json"),
        }
        self.set("module_meta", module_meta)
        self.load_modules()

    ####################################################################################
    # Initialization and Properties
    ####################################################################################
    @property
    def config_path(self) -> Path | None:
        """Path to the config-file."""
        if self._config_path is None:
            # Initialize setting of the config_path
            logging.info("No config_path set, initializing.")
            self.config_path = None
        return self._config_path

    @config_path.setter
    def config_path(self, value):
        """Set the path to the config-file (respects interactive mode)."""
        # Check existence and prompt user for a new config-file if needed
        if value is None or not isfile(value):
            if value is None:
                logging.warning("No config-file path set!")
            else:
                logging.warning(f"Config file {value} does not exist!")
            ans = ask_user(
                "Do you want to create a new config-file? (or use an existing one)",
                close_on_cancel=True,
            )
            if ans is None:  # user cancelled
                logging.info("User canceled, closing app.")
                sys.exit(0)
            elif ans:
                logging.info("Creating new config-file.")
                config_folder = get_user_input(
                    "Set the folder-path to store the config-file",
                    "folder",
                    exit_on_cancel=True,
                )
                name = get_user_input("Please enter a name for this project", "string")
                value = join(config_folder, f"{name}_config.json")
                with open(value, "w", encoding="utf-8") as file:
                    json.dump(default_config, file, indent=4, cls=TypedJSONEncoder)
            else:
                logging.info("Using existing config-file.")
                value = get_user_input(
                    "Please enter the path to an exisiting config-file",
                    "file",
                    file_filter="JSON files (*.json)",
                    exit_on_cancel=True,
                )
        # Set, load and persist
        self._config_path = Path(value)
        self._config_lock = FileLock(Path(self._config_path).with_suffix(".lock"))
        self.settings.set("config_path", value)

    @property
    def config_lock(self):
        if self._config_lock is None:
            logging.info("Config lock not set, initializing config_path.")
            self.config_path = None
        return self._config_lock

    def _load_config(self):
        """Load the configuration from the config-file if necessary."""
        try:
            with open(self.config_path) as file:
                config = json.load(file, object_hook=type_json_hook)
        except (
            OSError,
            json.JSONDecodeError,
            UnicodeDecodeError,
            FileNotFoundError,
        ) as err:
            logging.warning(
                f"Loading config from {self.config_path} failed with:\n{err}\nUsing defaults."
            )
            config = deepcopy(default_config)

        return config

    def _save_config(self, config) -> None:
        tmp_path = self._config_path.with_suffix(self._config_path.suffix + ".tmp")
        with open(tmp_path, "w") as file:
            json.dump(config, file, indent=4, cls=TypedJSONEncoder)
        os.replace(tmp_path, self._config_path)

    def default(self, key):
        """Get the default value for a specific key."""
        return deepcopy(default_config.get(key, None))

    def get(self, key, default=None) -> Any:
        """Load a specific key from the config-file."""
        try:
            with self.config_lock:
                config = self._load_config()
                return config.get(
                    key, self.default(key) if default is None else default
                )
        except Timeout:
            logging.warning(
                f"Could not acquire lock for settings after {self.lock_timeout} seconds. Using defaults."
            )
        return self.default(key)

    def set(self, key, value) -> None:
        """Set a specific key in the config-file."""
        try:
            with self.config_lock:
                config = self._load_config()
                config[key] = value
                self._save_config(config)
        except Timeout:
            logging.error(
                f"Could not acquire lock for settings file after {self.lock_timeout} seconds. Changes not saved."
            )

    def __getattr__(self, name) -> Any:
        """Get attributes from the config-file if possible."""
        if name in default_config:
            return self.get(name)
        else:
            raise AttributeError(f"Controller has no attribute '{name}'")

    def __setattr__(self, name, value) -> None:
        """Set attributes in the config-file if possible."""
        # Check for instance attributes first to avoid recursion during __init__
        if name in (
            "settings",
            "_config_path",
            "_config_lock",
            "lock_timeout",
            "modules",
            "_process_count",
        ):
            super().__setattr__(name, value)
        elif name in default_config:
            self.set(name, value)
        else:
            super().__setattr__(name, value)

    @property
    def data_root(self) -> Path:
        """Path to the root data directory.

        This is the root folder of the processed data.
        """
        data_root = self.settings.get("data_root")
        if data_root is not None and not isdir(data_root):
            raise_user_attention(
                f"Path {data_root} does not exist! If you moved from another device, please select the data-root folder."
            )
        if data_root is None or not isdir(data_root):
            data_root = get_user_input(
                "Please select/create a folder for the data-root.", "folder"
            )
            self.data_root = data_root

        return Path(data_root)

    @data_root.setter
    def data_root(self, value: Optional[Union[str, Path]]) -> None:
        if value is not None:
            if not isdir(value):
                raise ValueError(f"Path {value} does not exist!")
            self.settings.set("data_root", value)

    @property
    def data_path(self) -> Path:
        """Path to the (processed) data directory.

        This contatins all data, mne-nodes works with. The original data
        are generally left unchanged.
        """
        data_path = self.data_root / self.name
        if not isdir(data_path):
            data_path.mkdir(parents=True, exist_ok=True)
        return data_path

    @property
    def subjects_dir(self) -> Path:
        """Path to the FreeSurfer subjects directory."""
        if is_test():
            subjects_dir = self.settings.get("subjects_dir", None)
        else:
            subjects_dir = mne.get_config("SUBJECTS_DIR", None)
        if subjects_dir is not None and not isdir(subjects_dir):
            raise_user_attention(
                f"Path {subjects_dir} does not exist! If you moved from another device, please select the folder where the FreeSurfer subjects directory is stored."
            )
        if subjects_dir is None or not isdir(subjects_dir):
            subjects_dir = get_user_input(
                "Please enter the path to the FreeSurfer subjects directory", "folder"
            )
            self.subjects_dir = subjects_dir

        return Path(subjects_dir)

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
    def plot_root(self):
        """Path to the directory where plots are saved."""
        plot_root = self.settings.get("plot_root", None)
        if plot_root is not None and not isdir(plot_root):
            raise_user_attention(
                f"Path {plot_root} does not exist! If you moved from another device, please select/create the folder where plots should be saved."
            )
        if plot_root is None or not isdir(plot_root):
            plot_root = get_user_input(
                "Please select/create a folder for saving plots.", "folder"
            )
            self.plot_root = plot_root
        return Path(plot_root)

    @plot_root.setter
    def plot_root(self, value):
        if value is not None:
            if not isdir(value):
                raise ValueError(f"Path {value} does not exist!")
            self.settings.set("plot_root", value)

    @property
    def plot_path(self):
        """Path to the plot directory for the current project."""
        plot_path = self.plot_root / self.name
        if not isdir(plot_path):
            plot_path.mkdir(parents=True, exist_ok=True)
        return plot_path

    @property
    def name(self):
        name = self.get("name", None)
        if name is None:
            name = get_user_input("Please enter a name for this project", "string")
        return name

    @name.setter
    def name(self, new_name):
        old_name = self.get("name")
        if old_name != new_name:
            # Rename the config file if the name changes
            old_path = self._config_path
            new_path = join(os.path.dirname(old_path), f"{new_name}_config.json")
            if os.path.exists(old_path):
                os.rename(old_path, new_path)
            self._config_path = new_path
        self.set("name", new_name)

    @property
    def local_config_path(self):
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

    def add_data(
        self,
        name: str,
        data_type: str,
        group: str = "All",
        input_path: Path | str | NoneType = None,
    ) -> None:
        """Add an input to the inputs dictionary.

        Parameters
        ----------
        name : str
            Name of the input (e.g., subject name or ID).
        data_type : str
            Type of the input data. Must be one of the keys in
            self.get("input_types") (e.g., "raw", "fsmri").
        group : str, optional
            Group name for the input. Default is "All".
        input_path : Path or str or NoneType, optional
            Path to the input data file or directory. If provided,
            the data will be imported using the appropriate import function.
            Default is None.
        """
        if data_type not in self.input_types:
            raise ValueError(f"{data_type} is not valid data-type.")
        inputs = self.get("inputs")
        if group not in inputs[data_type]:
            inputs[data_type][group] = []
        if name in inputs[data_type][group]:
            logging.error(f"The input {name} is already in {group} for{data_type}.")
            return
        inputs[data_type][group].append(name)
        self.set("inputs", inputs)
        if input_path is not None:
            # ToDo: Implement import functions for other data types
            data_import = import_module("mne_nodes.pipeline.data_import")
            import_func = getattr(
                data_import, self.get("input_types")[data_type]["import"]
            )
            import_func(name=name, import_path=input_path, controller=self)

    def remove_data(self, name, data_type, group="All"):
        """Remove an input from the inputs dictionary."""
        if data_type not in self.input_types:
            raise ValueError(f"{data_type} is not valid data-type.")
        inputs = self.get("inputs")
        if group not in inputs[data_type]:
            logging.error(f"Group {group} does not exist for {data_type}.")
            return
        if name not in inputs[data_type][group]:
            logging.error(f"The input {name} is not in {group} for {data_type}.")
            return
        inputs[data_type][group].remove(name)
        if len(inputs[data_type][group]) == 0:
            del inputs[data_type][group]
        self.set("inputs", inputs)
        for dt in ["fsmri", "erm"]:
            self.input_mapping[dt].pop(name, None)
        if name in self.selected_inputs:
            self.selected_inputs.remove(name)
        self.bad_channels.pop(name, None)
        self.event_ids.pop(name, None)
        if data_type == "fsmri":
            data_type_dir = join(self.subjects_dir, name)
        else:
            data_type_dir = join(self.data_path, name)
        shutil.rmtree(data_type_dir, ignore_errors=True)

    def get_default(self, parameter_name: str) -> Any:
        """Get the default value for a given parameter name."""
        parameter_meta = self.parameter_metas.get(parameter_name)
        if parameter_meta is None:
            raise KeyError(f"Parameter '{parameter_name}' not found in Parameter-Meta.")
        default_value = parameter_meta["default"]

        return default_value

    def parameter(self, parameter_name: str, p_preset: Optional[str] = None) -> Any:
        """Get a specific parameter from the project parameters."""
        p_preset = p_preset or self.p_preset
        parameters = self.parameters
        if p_preset not in parameters:
            logging.warning(
                f"Parameter preset '{p_preset}' not found in project. "
                "Using 'Default' preset instead."
            )
            p_preset = "Default"
        if parameter_name not in parameters[p_preset]:
            logging.warning(
                f"Parameter '{parameter_name}' not found in preset '{p_preset}'. "
                "Setting and returning default value."
            )
            parameters[p_preset][parameter_name] = self.get_default(parameter_name)
            self.set("parameters", parameters)

        return parameters[p_preset][parameter_name]

    def set_parameter(
        self, parameter_name: str, value: Any, p_preset: Optional[str] = None
    ) -> None:
        """Set a specific parameter in the project parameters."""
        p_preset = p_preset or self.p_preset
        parameters = self.get("parameters")
        if p_preset not in parameters:
            logging.warning(
                f"Parameter preset '{p_preset}' not found in project. "
                "Using 'Default' preset instead."
            )
            p_preset = "Default"
        if parameter_name not in parameters[p_preset]:
            logging.warning(
                "You should not create a new parameter with controller.set_parameter. Add the parameter to the parameter-meta first. This function should only be used to modify existing parameters."
            )
        parameters[p_preset][parameter_name] = value
        self.set("parameters", parameters)

    def func_parameters(self, function_name, p_preset=None):
        """Get the parameters for a specific function from the project
        parameters."""
        p_preset = p_preset or self.p_preset
        if p_preset not in self.parameters:
            logging.warning(
                f"Parameter preset '{p_preset}' not found in project. "
                "Using 'Default' preset instead."
            )
            p_preset = "Default"
        function_metas = self.get("function_metas")
        if function_name not in function_metas:
            raise KeyError(f"Function '{function_name}' not found in function meta.")

        func_meta = function_metas[function_name]
        params = {}
        for param_name in func_meta["parameters"]:
            params[param_name] = self.parameter(param_name, p_preset)

        return params

    ####################################################################################
    # Modules
    ####################################################################################
    def _load_module_config(self, module_name):
        """Load the configuration file for a module from the package path."""
        config_file_path = self.module_meta[module_name]["config"]
        if not isfile(config_file_path):
            raise RuntimeError(
                f"Config file for {module_name} not found at {config_file_path}."
            )
        with open(config_file_path) as file:
            config_data = json.load(file, object_hook=type_json_hook)
        function_metas = self.get("function_metas")
        function_metas.update(config_data["functions"])
        self.set("function_metas", function_metas)
        parameter_metas = self.get("parameter_metas")
        parameter_metas.update(config_data["parameters"])
        self.set("parameter_metas", parameter_metas)

    def _import_module(self, module_name):
        """Import a module from the given package path."""
        pkg_path = self.module_meta[module_name]["module"].parent
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
        self._load_module_config(module_name)

    def load_modules(self) -> None:
        """Load custom modules from their config files."""
        for module_name in self.module_meta:
            self._import_module(module_name)

    def add_custom_module(self, config_file_path: Union[str, Path]):
        """Add a custom module to the controller.

        Parameters
        ----------
        config_file_path : str or Path
            Path to the configuration file for the custom module.
        """
        with open(config_file_path) as file:
            config_data = json.load(file, object_hook=type_json_hook)
        module_name = config_data.get("module_name", None)
        if module_name is None:
            raise ValueError(
                f"Config file {config_file_path} does not contain a 'module_name' entry."
            )
        if not isfile(config_file_path):
            raise FileNotFoundError(f"Config file {config_file_path} does not exist.")
        module_path = Path(config_file_path).parent / f"{module_name}.py"
        if not isfile(module_path):
            raise FileNotFoundError(
                f"Module file {module_path} does not exist. The module file has to have the exact name of the module and the config file has to be named <module_name>_config.json."
            )
        module_meta = self.get("module_meta")
        module_meta[module_name] = {
            "config": config_file_path,
            "module": Path(config_file_path).parent / f"{module_name}.py",
        }
        self.set("module_meta", module_meta)
        self.load_modules()

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

    def get_meta(self, name: str) -> Dict[str, Any]:
        """Get the metadata for a specific parameter or function."""
        if name in self.parameter_metas:
            return self.parameter_metas[name]
        elif name in self.function_metas:
            return self.function_metas[name]
        else:
            raise KeyError(f"Metadata for '{name}' not found in project.")

    @staticmethod
    def _get_func_start_end(function_name, module_code):
        tree = ast.parse(module_code)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == function_name:
                # lineno and end_lineno are 1-based
                start_line = node.lineno - 1
                end_line = node.end_lineno - 1

                return start_line, end_line
        logging.warning("Could not find function in module code.")

        return None, None

    def get_function_code(self, function_name: str):
        """Get the code for a specific function from the modules."""
        module_name = self.get_meta(function_name)["module"]
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

    def convert_to_code(self, instructions, start_name):
        """Convert a list of instructions to a Python code string."""
        # Resolve imports
        code = (
            "# This code was generated by mne-nodes\n\n"
            "import traceback\n"
            "from tqdm import tqdm\n"
            "import mne_nodes\n"
            "from mne_nodes.pipeline.controller import Controller\n"
            "from mne_nodes.pipeline.loading import MEEG, FSMRI, Group\n\n"
            "# Disable gui-mode\n"
            "mne_nodes.gui_mode = False\n\n"
            "# Load controller\n"
            f"ct = Controller(config_path='{self.config_path.as_posix()}')\n\n"
            "# Inject modules into global namespace\n"
            "globals().update(ct.modules)\n"
        )
        # Add module imports
        for module_name, module in self.modules.items():
            code += f"from {module_name} import *\n"
        # Add function execution code
        code += "\n# Execute pipeline\n"
        # ToDo: Put into try-except block to catch errors of multiple subjects
        loaded_data = set()
        modules = {}
        if instructions[0][0] == "raw":
            code += f"for meeg_name in tqdm(ct.get('inputs')['raw']['{start_name}']):\n"
            code += self.tab + "meeg = MEEG(meeg_name, ct)\n"
            loaded_data.add(instructions[0][0])
        elif instructions[0][0] == "fsmri":
            code += (
                f"for fsmri_name in tqdm(ct.get('inputs')['fsmri']['{start_name}']):\n"
            )
            code += self.tab + "fsmri = FSMRI(fsmri_name, ct)\n"
        elif instructions[0][0] == "group":
            pass  # ToDo: Handle groups
        else:
            raise ValueError(f"Unknown input type: {instructions[0][0]}")
        # Add try-except block for error handling
        code += self.tab + "try:\n"
        for name, kind in instructions:
            if kind == "Input" and name not in loaded_data:
                code += self.tab * 2 + f'{kind} = meeg.load(data_type="{kind}")\n'
                loaded_data.add(name)
            elif kind == "Function":
                meta = self.get_meta(name)
                if meta["module"] not in modules:
                    modules[meta["module"]] = []
                modules[meta["module"]].append(name)
                code += self.tab * 2 + f"{name}(meeg, **ct.func_parameters('{name}'))\n"
            else:
                logging.warning(
                    f"Unknown instruction type '{kind}' for name '{name}'. "
                    "Skipping this instruction."
                )
        code += self.tab + "except Exception as e:\n"
        code += self.tab * 2 + "print(f'[Error] for {meeg_name}: {e}')\n"
        code += self.tab * 2 + "traceback.print_exc()\n"
        code += self.tab * 2 + "continue\n"

        return code

    def start(self, instructions, start_name):
        # Generate code file
        code = self.convert_to_code(instructions, start_name)
        run_file_path = self.local_config_path / f"{self.name}_pipeline.py"
        with open(run_file_path, "w") as file:
            file.write(code)
        # Add Process to ConsoleDock and get Console
        console = self.main_window.console_dock.add_process()
        process = Process(
            proc_id=self._process_count,
            console=console,
            working_directory=self.data_path,
            self_destruct=True,
        )
        self._process_count += 1
        # Start process
        process.start(sys.executable, [str(run_file_path)])

    ####################################################################################
    # Legacy
    ####################################################################################
    def load_project(self, project_name, old_controller):
        """Load an (old) project and get config data.

        Changes:
        - Groups are represented by lists of inputs
        (thus each group should have a separate input node)
        - Input mappings are pooled together (meeg_to_erm, meeg_to_fsmri, etc.)
        - Pandas DataFrames for parameter- and function-metadata
        are turned into dictionaries
        """
        from mne_nodes.pipeline.legacy import (
            OldController,
            Project,
            convert_pandas_meta,
        )

        if isinstance(old_controller, str):
            ct = OldController(
                home_path=old_controller,
                selected_project=project_name,
                edu_program_name=None,
            )
        else:
            ct = old_controller
        pr = Project(ct, project_name)
        self.name = pr.name
        self.data_root = pr.data_path
        self.subjects_dir = ct.subjects_dir
        self.plot_root = pr.figures_path
        # ToDo Next: Legacy conversion
        # Add inputs (and split groups into multiple input nodes)
        for group_name, names in pr.all_groups.items():
            self.viewer.add_input_node("MEEG", group_name)
        self.all_groups = pr.all_groups
        self.all_meeg = pr.all_meeg
        self.all_fsmri = pr.all_fsmri
        self.all_erm = pr.all_erm
        self.sel_meeg = pr.sel_meeg
        self.sel_fsmri = pr.sel_fsmri
        self.bad_channels = pr.meeg_bad_channels
        self.event_ids = pr.meeg_event_id
        self.sel_event_id = pr.sel_event_id
        self.ica_exclude = pr.meeg_ica_exclude
        self.meeg_to_erm = pr.meeg_to_erm
        self.meeg_to_fsmri = pr.meeg_to_fsmri
        self.parameters = pr.parameters
        self.p_preset = pr.p_preset

        # Get function meta
        new_module_meta = convert_pandas_meta(ct.pd_funcs, ct.pd_params)
        module_meta = self.get("module_meta")
        module_meta.update(new_module_meta)
        self.set("module_meta", module_meta)

        for func in pr.sel_functions:
            self.viewer.add_function_node(func)

    def convert_custom_package(self, package_name):
        # ToDo: Convert a custom package to the new format
        pass
