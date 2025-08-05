"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import json
import logging
import os
import re
import sys
from importlib import import_module
from importlib.util import cache_from_source
from inspect import getsource
from os.path import isdir, join, isfile
from pathlib import Path

import mne

from mne_nodes.basic_operations import basic_operations
from mne_nodes.basic_plot import basic_plot
from mne_nodes.gui.gui_utils import get_user_input, ask_user
from mne_nodes.pipeline.legacy import convert_pandas_meta, OldController, Project
from mne_nodes.pipeline.io import TypedJSONEncoder, type_json_hook
from mne_nodes.pipeline.settings import Settings


class Controller:
    """New controller, that combines the former old controller and project
    class and loads a controller for each "project".

    The home-path structure should no longer be as rigid as before, just specifying the
    path to meeg- and fsmri-data. For each controller, there is a config-file stored,
    where paths to the meeg-data, the freesurfer-dir and the custom-packages are stored.

    Parameters
    ----------
    config_path : str or Path, optional
        Path to the config-file, if
    data_path : str or Path, optional
        Path to the (processed) data directory. This contatins all data, mne-nodes works with.
    subjects_dir : str or Path, optional
        Path to the FreeSurfer MRI data root directory, by default None.
        Will be read and written to the mne config file.

    Attributes
    ----------
    config_path : str or Path
        Path to the config-file.
    config : dict
        Dictionary containing the configuration data loaded from the config-file.
    """

    def __init__(self, config_path=None, data_path=None, subjects_dir=None):
        self._config_path = config_path or Settings().value(
            "config_path", defaultValue=None
        )
        self._config = {}
        # The device dependent settings
        self.settings = Settings()
        self.data_path = data_path
        self.subjects_dir = subjects_dir
        self.default_config = {
            "selected_modules": ["basic_operations", "basic_plot"],
            "parameter_preset": "Default",
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
        }

        # Property attributes
        self._modules = {}
        self._function_metas = {}
        self._parameter_metas = {}
        self._input_nodes = {k: {} for k in self.input_data_types}
        self._function_nodes = {}

        # Initialize modules
        self.load_basic_modules()
        self.load_custom_modules()

    ####################################################################################
    # Initialization and Properties
    ####################################################################################
    @property
    def config_path(self):
        """Path to the config-file."""
        if self._config_path is None:
            logging.warning("No config-file path set!")
            ans = ask_user("Do you want to create a new config-file?")
            if ans:
                logging.info("Creating new config-file.")
                config_folder = get_user_input(
                    "Set the folder-path to store the config-file", "folder"
                )
                self.config_path = config_folder
                self.save_config()
            else:
                logging.info("Using existing config-file.")
                self.config_path = get_user_input(
                    "Please enter the path to an exisiting config-file",
                    "file",
                    file_filter="JSON files (*.json)",
                )

        return self._config_path

    @config_path.setter
    def config_path(self, value):
        if isdir(value):
            # If the config_path is a directory, create a default config file path
            self._config_path = join(value, f"{self.name}_config.json")
        else:
            # If the config_path is a filename, set it directly
            self._config_path = value

    @property
    def config(self):
        """Configuration dictionary loaded from the config-file."""
        if not self._config:
            with open(self.config_path) as file:
                self._config = json.load(file, object_hook=type_json_hook)
        # Set defaults
        for config_key, value in self.default_config.items():
            if config_key not in self._config:
                self._config[config_key] = value
        return self._config

    def save_config(self):
        with open(self._config_path, "w") as file:
            json.dump(self._config, file, indent=4, cls=TypedJSONEncoder)

    @property
    def data_path(self):
        """Path to the (processed) data directory.

        This contatins all data, mne-nodes works with. The original data
        are generally left unchanged.
        """
        return self.settings.value("data_path")

    @data_path.setter
    def data_path(self, value):
        if value is not None:
            if not isdir(value):
                raise ValueError(f"Path {value} does not exist!")
            self.settings.setValue("data_path", value)

    @property
    def subjects_dir(self):
        """Path to the FreeSurfer subjects directory."""
        subjects_dir = mne.get_config("SUBJECTS_DIR", None)
        if subjects_dir is None:
            subjects_dir = get_user_input(
                "Please enter the path to the FreeSurfer subjects directory", "folder"
            )
            self.subjects_dir = subjects_dir
        return subjects_dir

    @subjects_dir.setter
    def subjects_dir(self, value):
        if value is not None:
            if not isdir(value):
                raise ValueError(f"Path {value} does not exist!")
            mne.set_config("SUBJECTS_DIR", value)

    @property
    def plot_path(self):
        plot_path = self.settings.value("plot_path")
        if plot_path is None:
            plot_path = get_user_input(
                "Please enter the path to store the plots", "folder"
            )
            self.plot_path = plot_path
        return plot_path

    @plot_path.setter
    def plot_path(self, value):
        if value is not None:
            if not isdir(value):
                raise ValueError(f"Path {value} does not exist!")
            self.settings.setValue("plot_path", value)

    @property
    def name(self):
        if "name" not in self._config:
            self.name = get_user_input("Please enter a name for this project", "string")

        return self._config["name"]

    @name.setter
    def name(self, new_name):
        old_name = self._config.get("name", None)
        if old_name is not None and old_name != new_name:
            # Rename the config file if the name changes
            old_path = self._config_path
            new_path = join(os.path.dirname(old_path), f"{new_name}_config.json")
            if os.path.exists(old_path):
                os.rename(old_path, new_path)
            self._config_path = new_path
        self._config["name"] = new_name

    @property
    def input_data_types(self):
        """This holds the input data types for the project.

        Keys are the data-type while values are the names/aliases of the
        data-type
        """
        if "input_data_types" not in self.config:
            self.config["input_data_types"] = {
                "raw": "MEG/EEG",
                "fsmri": "Freesurfer MRI",
            }
            self.save_config()
        return self.config["input_data_types"]

    @property
    def inputs(self):
        """This holds all data input nodes from MEEG and FSMRI data.

        There can be multiple input-nodes for each data type with each
        having a distinct name (keys in the second level of the
        dictionary).
        """
        if "inputs" not in self.config:
            self.config["inputs"] = {k: {} for k in self.input_data_types}
        return self.config["inputs"]

    @property
    def selected_inputs(self):
        """This holds all selected inputs."""
        if "selected_inputs" not in self.config:
            self.config["selected_inputs"] = []
        return self.config["selected_inputs"]

    @property
    def input_mapping(self):
        """This holds the mapping of input nodes to data types (like MRI or
        Empty- Room)."""
        if "input_mapping" not in self.config:
            self.config["input_mapping"] = {}
        return self.config["input_mapping"]

    @property
    def bad_channels(self):
        """This holds all bad channels for MEEG data.

        Maybe this is obsolete with mne-bids.
        """
        if "bad_channels" not in self.config:
            self.config["bad_channels"] = {}
        return self.config["bad_channels"]

    @property
    def event_ids(self):
        """This holds all event ids for MEEG data.

        Maybe this is obsolete with mne-bids.
        """
        if "event_ids" not in self.config:
            self.config["event_ids"] = {}
        return self.config["event_ids"]

    @property
    def selected_event_ids(self):
        """This holds all selected event ids for MEEG data.

        Maybe this is obsolete with mne-bids.
        """
        if "selected_event_ids" not in self.config:
            self.config["selected_event_ids"] = {}
        return self.config["selected_event_ids"]

    @property
    def ica_exclude(self):
        """This holds the ICA-excluded components for MEEG data."""
        if "ica_exclude" not in self.config:
            self.config["ica_exclude"] = {}
        return self.config["ica_exclude"]

    @property
    def parameters(self):
        """This holds the parameters for the project."""
        if "parameters" not in self.config:
            self.config["parameters"] = {self.parameter_preset: {}}
        return self.config["parameters"]

    @property
    def parameter_metas(self):
        """This holds the metadata for the parameters."""
        return self._parameter_metas

    @property
    def parameter_preset(self):
        """This holds the current parameter preset for the project."""
        if "parameter_preset" not in self.config:
            self.config["parameter_preset"] = "Default"
        return self.config["parameter_preset"]

    @parameter_preset.setter
    def parameter_preset(self, value):
        """Set the current parameter preset for the project."""
        if value not in self.parameters:
            raise KeyError(f"Parameter preset '{value}' not found in project.")
        self.config["parameter_preset"] = value
        self.save_config()

    def get_default(self, parameter_name):
        """Get the default value for a given parameter name."""
        parameter_meta = self.parameter_metas.get(parameter_name, None)
        if parameter_meta is None:
            raise KeyError(f"Parameter '{parameter_name}' not found in Parameter-Meta.")
        default_value = parameter_meta["default"]

        return default_value

    def parameter(self, parameter_name, parameter_preset=None):
        """Get a specific parameter from the project parameters."""
        parameter_preset = parameter_preset or self.parameter_preset
        if parameter_preset not in self.parameters:
            logging.warning(
                f"Parameter preset '{parameter_preset}' not found in project. "
                "Using 'Default' preset instead."
            )
            parameter_preset = "Default"
        if parameter_name not in self.parameters[parameter_preset]:
            logging.warning(
                f"Parameter '{parameter_name}' not found in preset '{parameter_preset}'. "
                "Returning default value."
            )
            return self.get_default(parameter_name)

        return self.parameters[parameter_preset][parameter_name]

    @property
    def add_kwargs(self):
        """This holds additional keyword arguments for the project."""
        if "add_kwargs" not in self.config:
            self.config["add_kwargs"] = {}
        return self.config["add_kwargs"]

    @property
    def plot_files(self):
        """This holds the plot file-paths for the project."""
        if "plot_files" not in self.config:
            self.config["plot_files"] = {}
        return self.config["plot_files"]

    ####################################################################################
    # Modules
    ####################################################################################
    @property
    def function_metas(self):
        """This holds the metadata for the functions used in the project.

        Only unique function names are allowed accross basic and custom
        packages.
        """
        return self._function_metas

    @property
    def modules(self):
        """This holds all modules used in the project."""
        return self._modules

    @property
    def custom_module_meta(self):
        """This holds the custom modules used in the project, stored by name
        and path to the config-file."""
        if "custom_module_meta" not in self.config:
            self.config["custom_module_meta"] = {}
        return self.config["custom_module_meta"]

    def _load_module_config(self, module_name, pkg_path):
        """Load the configuration file for a module from the package path."""
        config_file_path = join(pkg_path, f"{module_name}_config.json")
        if not isfile(config_file_path):
            raise RuntimeError(
                f"Config file for {module_name} not found at {config_file_path}."
            )
        with open(config_file_path) as file:
            config_data = json.load(file, object_hook=type_json_hook)
        self.function_metas.update(config_data["functions"])
        self.parameter_metas.update(config_data["parameters"])

    def _import_module(self, module_name, pkg_path):
        """Import a module from the given package path."""
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
            self._modules[module_name] = module
        # Load the config file for the basic module
        self._load_module_config(module_name, pkg_path)

    def load_basic_modules(self):
        """Load the basic modules from the basic_operations package."""
        for module in [basic_operations, basic_plot]:
            module_name = module.__name__.split(".")[-1]  # Get the module name
            self._modules[module_name] = module
            pkg_path = Path(module.__file__).parent
            self._load_module_config(module_name, pkg_path)

    def load_custom_modules(self):
        """Load custom modules from their config files."""
        for module_name, config_file_path in self.custom_module_meta.items():
            pkg_path = Path(config_file_path).parent
            self._import_module(module_name, pkg_path)

    def add_custom_module(self, config_file_path):
        """Add a custom module to the controller.

        Parameters
        ----------
        config_file_path : str or Path
            Path to the configuration file for the custom module.
        """
        module_name = Path(config_file_path).stem.replace("_config", "")
        if not isfile(config_file_path):
            raise FileNotFoundError(f"Config file {config_file_path} does not exist.")
        module_path = Path(config_file_path).parent / f"{module_name}.py"
        if not isfile(module_path):
            raise FileNotFoundError(
                f"Module file {module_path} does not exist. The module file has to have the exact name of the module and the config file has to be named <module_name>_config.json."
            )

        self.custom_module_meta[module_name] = config_file_path
        self.load_custom_modules()

    def reload_modules(self, module_name=None):
        """Reload all modules in the controller.

        This method reloads the selected module or all modules in the controller by removing them from sys.modules
        and importing them again. This ensures that any changes to the module's source code
        are reflected in the controller.

        Parameters
        ----------
        module_name : str, None, optional
            Provide a module_name (must be unique) to be reloaded.

        Note:
        -----
        This method updates the modules in the controller, but it does not update existing
        references to objects from the modules. If you have a reference to an object from
        a module (like a function), you need to get a new reference to that object after
        reloading the module using controller.modules[<module>].

        Example:
        --------
        >>> # Get a reference to a function
        >>> controller = Controller()
        >>> func = controller.modules["module_name"].some_func
        >>> # Modify the module's source code
        >>> controller.reload_modules()
        >>> # Get a new reference to the function
        >>> updated_func = controller.modules["module_name"].some_func
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
            self._modules[module_name] = new_module

    def get_meta(self, name):
        """Get the metadata for a specific parameter or function."""
        if name in self.parameter_metas:
            return self.parameter_metas[name]
        elif name in self.function_metas:
            return self.function_metas[name]
        else:
            raise KeyError(f"Metadata for '{name}' not found in project.")

    def get_function_code(self, function_name):
        """Get the code for a specific function from the modules."""
        module_name = self.get_meta(function_name)["module"]
        module = self.modules[module_name]
        function = getattr(module, function_name)
        if function is None:
            raise KeyError(
                f"Function '{function_name}' not found in module '{module_name}'."
            )
        code = getsource(function)
        module_code = getsource(module)
        # ToDo: Get start/end lines of the function code in module
        re.search(code, module_code)
        pass

        return None, None, None

    ####################################################################################
    # Node Management
    ####################################################################################
    @property
    def input_nodes(self):
        return self._input_nodes

    @property
    def function_nodes(self):
        """This maps the node(s) to each function used in the project (by name
        and id)."""
        return self._function_nodes

    def selected_nodes(self):
        """This holds the selected nodes for the project (by id)."""
        if "selected_nodes" not in self.config:
            self.config["selected_nodes"] = []
        return self.config["selected_nodes"]

    def init_input_nodes(self):
        """Initialize input nodes from the Project."""
        # ToDo Next: Start and add input nodes for project configuration
        pass

    def init_function_nodes(self):
        """Initialize function nodes from the Project."""
        # ToDo Next: Start and add function nodes for project configuration
        pass

    def init_connections(self):
        """Initialize connections between input nodes and function nodes."""
        # ToDo Next: Start and establish connections between input nodes and
        #  function nodes
        pass

    def init_nodes(self):
        """Initialize all nodes in the controller."""

        self.init_input_nodes()
        self.init_function_nodes()
        self.init_connections()

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
        self.data_path = pr.data_path
        self.subjects_dir = ct.subjects_dir
        self.plot_path = pr.figures_path

        # Add inputs (and split groups into multiple input nodes)
        for group_name, names in pr.all_groups.items():
            self.inputs["raw"][group_name] = names
            self.viewer.add_input_node("MEEG", group_name)
        self.inputs["raw"]["All"].extend(pr.all_meeg)
        self.selected_inputs.extend(pr.sel_meeg)

        # Add Empty-Room data if available
        if len(pr.all_erm) > 0:
            self.inputs["raw"]["Empty-Room"] = pr.all_erm

        self.inputs["fsmri"]["All"].extend(pr.all_fsmri)
        self.selected_inputs.extend(pr.sel_fsmri)

        self.config["bad_channels"] = pr.meeg_bad_channels
        self.config["event_ids"] = pr.meeg_event_id
        self.config["selected_event_ids"] = pr.sel_event_id
        self.config["ica_exclude"] = pr.meeg_ica_exclude

        self.config["input_mapping"].update(pr.meeg_to_erm)
        self.config["input_mapping"].update(pr.meeg_to_fsmri)

        self.config["parameters"].update(pr.parameters)
        self.config["parameter_preset"] = pr.parameter_preset

        # Get function meta
        func_metas = convert_pandas_meta(ct.pd_funcs, ct.pd_params)
        for module_name, func_meta in func_metas.items():
            for func_name, meta in func_meta["functions"].items():
                self._function_metas[func_name] = meta

        for func in pr.sel_functions:
            self.viewer.add_function_node(func)

    def convert_custom_package(self, package_name):
        # ToDo: Convert a custom package to the new format
        pass
