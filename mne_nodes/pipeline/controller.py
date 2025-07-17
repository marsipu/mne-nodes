"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import json
import logging
import os
import re
import shutil
import sys
import traceback
from importlib import reload, resources, import_module
from importlib.util import cache_from_source
from inspect import getsource
from os import listdir
from os.path import isdir, join, isfile
from pathlib import Path

import mne
import pandas as pd

from mne_nodes import basic_functions, extra
from mne_nodes.gui.gui_utils import get_user_input, ask_user
from mne_nodes.pipeline.legacy import (
    transfer_file_params_to_single_subject,
    convert_pandas_meta,
)
from mne_nodes.pipeline.pipeline_utils import (
    QS,
    logger,
    type_json_hook,
    TypedJSONEncoder,
)
from mne_nodes.pipeline.project import Project

home_dirs = ["custom_packages", "freesurfer", "projects"]
project_dirs = ["_pipeline_scripts", "data", "figures"]


class OldController:
    def __init__(self, home_path=None, selected_project=None, edu_program_name=None):
        # Check Home-Path
        self.pr = None
        # Try to load home_path from QSettings
        self.home_path = home_path or QS().value("home_path", defaultValue=None)
        self.settings = {}
        if self.home_path is None:
            raise RuntimeError("No Home-Path found!")

        # Check if path exists
        elif not isdir(self.home_path):
            raise RuntimeError(f"{self.home_path} not found!")

        # Check, if path is writable
        elif not os.access(self.home_path, os.W_OK):
            raise RuntimeError(f"{self.home_path} not writable!")

        # Initialize log-file
        self.logging_path = join(self.home_path, "_pipeline.log")
        file_handlers = [h for h in logger().handlers if h.name == "file"]
        if len(file_handlers) > 0:
            logger().removeHandler(file_handlers[0])
        file_handler = logging.FileHandler(self.logging_path, "w")
        file_handler.set_name("file")
        logger().addHandler(file_handler)

        logger().info(f"Home-Path: {self.home_path}")
        QS().setValue("home_path", self.home_path)
        # Create subdirectories if not existing for a valid home_path
        for subdir in [d for d in home_dirs if not isdir(join(self.home_path, d))]:
            os.mkdir(join(self.home_path, subdir))

        # Get Project-Folders (recognized by distinct sub-folders)
        self.projects_path = join(self.home_path, "projects")
        self.projects = [
            p
            for p in listdir(self.projects_path)
            if all([isdir(join(self.projects_path, p, d)) for d in project_dirs])
        ]

        # Initialize Subjects-Dir
        self.subjects_dir = join(self.home_path, "freesurfer")
        mne.utils.set_config("SUBJECTS_DIR", self.subjects_dir, set_env=True)

        # Initialize folder for custom packages
        self.custom_pkg_path = join(self.home_path, "custom_packages")

        # Initialize educational programs
        self.edu_program_name = edu_program_name
        self.edu_program = None

        # Load default settings
        default_path = join(resources.files(extra), "default_settings.json")
        with open(default_path) as file:
            self.default_settings = json.load(file)

        # Load settings (which are stored as .json-file in home_path)
        # settings=<everything, that's OS-independent>
        self.load_settings()

        # Initialize data types (like "raw", "epochs", etc.)
        self._data_types = []

        self.all_modules = {}
        self.all_pd_funcs = None

        # Pandas-DataFrame for contextual data of basic functions
        # (included with program)
        self.pd_funcs = pd.read_csv(
            resources.files(extra) / "functions.csv",
            sep=";",
            index_col=0,
            na_values=[""],
            keep_default_na=False,
        )

        # Pandas-DataFrame for contextual data of parameters
        # for basic functions (included with program)
        self.pd_params = pd.read_csv(
            resources.files(extra) / "parameters.csv",
            sep=";",
            index_col=0,
            na_values=[""],
            keep_default_na=False,
        )

        # Import the basic- and custom-function-modules
        self.import_custom_modules()

        # Check Project
        if selected_project is None:
            selected_project = self.settings["selected_project"]

        if selected_project is None:
            if len(self.projects) > 0:
                selected_project = self.projects[0]

        # Initialize Project
        if selected_project is not None:
            self.change_project(selected_project)

    @property
    def data_types(self):
        return self._data_types

    def load_settings(self):
        try:
            with open(join(self.home_path, "mne_nodes-settings.json")) as file:
                self.settings = json.load(file)
            # Account for settings, which were not saved
            # but exist in default_settings
            for setting in [
                s for s in self.default_settings["settings"] if s not in self.settings
            ]:
                self.settings[setting] = self.default_settings["settings"][setting]
        except FileNotFoundError:
            self.settings = self.default_settings["settings"]
        else:
            # Check integrity of Settings-Keys
            s_keys = set(self.settings.keys())
            default_keys = set(self.default_settings["settings"])
            # Remove additional (old) keys not appearing in default-settings
            for setting in s_keys - default_keys:
                self.settings.pop(setting)
            # Add new keys from default-settings
            # which are not present in settings
            for setting in default_keys - s_keys:
                self.settings[setting] = self.default_settings["settings"][setting]

        # Check integrity of QSettings-Keys
        QS().sync()
        qs_keys = set(QS().childKeys())
        qdefault_keys = set(self.default_settings["qsettings"])
        # Remove additional (old) keys not appearing in default-settings
        for qsetting in qs_keys - qdefault_keys:
            QS().remove(qsetting)
        # Add new keys from default-settings which are not present in QSettings
        for qsetting in qdefault_keys - qs_keys:
            QS().setValue(qsetting, self.default_settings["qsettings"][qsetting])

    def save_settings(self):
        try:
            with open(join(self.home_path, "mne_nodes-settings.json"), "w") as file:
                json.dump(self.settings, file, indent=4)
        except FileNotFoundError:
            logger().warning("Settings could not be saved!")

        # Sync QSettings with other instances
        QS().sync()

    def get_setting(self, setting):
        try:
            value = self.settings[setting]
        except KeyError:
            value = self.default_settings["settings"][setting]

        return value

    def change_project(self, new_project):
        self.pr = Project(self, new_project)
        self.settings["selected_project"] = new_project
        if new_project not in self.projects:
            self.projects.append(new_project)
        logger().info(f"Selected-Project: {self.pr.name}")
        # Legacy
        transfer_file_params_to_single_subject(self)

        return self.pr

    def remove_project(self, project):
        self.projects.remove(project)
        if self.pr.name == project:
            if len(self.projects) > 0:
                new_project = self.projects[0]
            else:
                new_project = get_user_input(
                    "Please enter the name of a new project!", "string", force=True
                )
            self.change_project(new_project)

        # Remove Project-Folder
        try:
            shutil.rmtree(join(self.projects_path, project))
        except OSError as error:
            print(error)
            logger().warning(
                f"The folder of {project} can't be deleted "
                f"and has to be deleted manually!"
            )

    def rename_project(self):
        check_writable = os.access(self.pr.project_path, os.W_OK)
        if check_writable:
            new_project_name = get_user_input(
                f'Change the name of project "{self.pr.name}" to:',
                "string",
                force=False,
            )
            if new_project_name is not None:
                try:
                    old_name = self.pr.name
                    self.pr.rename(new_project_name)
                except PermissionError:
                    # ToDo: Warning-Function for GUI with dialog and non-GUI
                    logger().critical(
                        f"Can't rename {old_name} to {new_project_name}. "
                        f"Probably a file from inside the project is still opened. "
                        f"Please close all files and try again."
                    )
                else:
                    self.projects.remove(old_name)
                    self.projects.append(new_project_name)
        else:
            logger().warning(
                "The project-folder seems to be not writable at the moment, "
                "maybe some files inside are still in use?"
            )

    def copy_parameters_between_projects(
        self,
        from_name,
        from_p_preset,
        to_name,
        to_p_preset,
        parameter=None,
    ):
        from_project = Project(self, from_name)
        if to_name == self.pr.name:
            to_project = self.pr
        else:
            to_project = Project(self, to_name)
        if parameter is not None:
            from_param = from_project.parameters[from_p_preset][parameter]
            to_project.parameters[to_p_preset][parameter] = from_param
        else:
            from_param = from_project.parameters[from_p_preset]
            to_project.parameters[to_p_preset] = from_param
        to_project.save()

    def save(self, worker_signals=None):
        if self.pr is not None:
            # Save Project
            self.pr.save(worker_signals)
            self.settings["selected_project"] = self.pr.name

        self.save_settings()

    def load_edu(self):
        if self.edu_program_name is not None:
            edu_path = join(self.home_path, "edu_programs", self.edu_program_name)
            with open(edu_path) as file:
                self.edu_program = json.load(file)

            self.all_pd_funcs = self.pd_funcs.copy()
            # Exclude functions which are not selected
            self.pd_funcs = self.pd_funcs.loc[
                self.pd_funcs.index.isin(self.edu_program["functions"])
            ]

            # Change the Project-Scripts-Path to a new folder
            # to store the Education-Project-Scripts separately
            self.pr.pscripts_path = join(
                self.pr.project_path, f'_pipeline_scripts{self.edu_program["name"]}'
            )
            if not isdir(self.pr.pscripts_path):
                os.mkdir(self.pr.pscripts_path)
            self.pr.init_pipeline_scripts()

            # Exclude MEEG
            self.pr._all_meeg = self.pr.all_meeg.copy()
            self.pr.all_meeg = [
                meeg for meeg in self.pr.all_meeg if meeg in self.edu_program["meeg"]
            ]

            # Exclude FSMRI
            self.pr._all_fsmri = self.pr.all_fsmri.copy()
            self.pr.all_fsmri = [
                meeg for meeg in self.pr.all_meeg if meeg in self.edu_program["meeg"]
            ]

    def import_custom_modules(self):
        """Load all modules in functions and custom_functions."""

        # Load basic-modules
        # Add functions to sys.path
        sys.path.insert(0, str(Path(basic_functions.__file__).parent))
        basic_functions_list = [x for x in dir(basic_functions) if "__" not in x]
        self.all_modules["basic"] = []
        for module_name in basic_functions_list:
            self.all_modules["basic"].append(module_name)

        # Load custom_modules
        pd_functions_pattern = r".*_functions\.csv"
        pd_parameters_pattern = r".*_parameters\.csv"
        custom_module_pattern = r"(.+)(\.py)$"
        for directory in [
            d for d in os.scandir(self.custom_pkg_path) if not d.name.startswith(".")
        ]:
            pkg_name = directory.name
            pkg_path = directory.path
            file_dict = {"functions": None, "parameters": None, "modules": []}
            for file_name in [
                f for f in listdir(pkg_path) if not f.startswith((".", "_"))
            ]:
                functions_match = re.match(pd_functions_pattern, file_name)
                parameters_match = re.match(pd_parameters_pattern, file_name)
                custom_module_match = re.match(custom_module_pattern, file_name)
                if functions_match:
                    file_dict["functions"] = join(pkg_path, file_name)
                elif parameters_match:
                    file_dict["parameters"] = join(pkg_path, file_name)
                elif custom_module_match and custom_module_match.group(1) != "__init__":
                    file_dict["modules"].append(custom_module_match)

            # Check, that there is a whole set for a custom-module
            # (module-file, functions, parameters)
            if all([value is not None or value != [] for value in file_dict.values()]):
                self.all_modules[pkg_name] = []
                functions_path = file_dict["functions"]
                parameters_path = file_dict["parameters"]
                correct_count = 0
                for module_match in file_dict["modules"]:
                    module_name = module_match.group(1)
                    # Add pkg-path to sys.path
                    sys.path.insert(0, pkg_path)
                    try:
                        import_module(module_name)
                    except Exception:
                        traceback.print_exc()
                    else:
                        correct_count += 1
                        # Add Module to dictionary
                        self.all_modules[pkg_name].append(module_name)

                # Make sure, that every module in modules
                # is imported without error
                # (otherwise don't append to pd_funcs and pd_params)
                if len(file_dict["modules"]) == correct_count:
                    try:
                        read_pd_funcs = pd.read_csv(
                            functions_path,
                            sep=";",
                            index_col=0,
                            na_values=[""],
                            keep_default_na=False,
                        )
                        read_pd_params = pd.read_csv(
                            parameters_path,
                            sep=";",
                            index_col=0,
                            na_values=[""],
                            keep_default_na=False,
                        )
                    except Exception:
                        traceback.print_exc()
                    else:
                        # Add pkg_name here (would be redundant
                        # in read_pd_funcs of each custom-package)
                        read_pd_funcs["pkg_name"] = pkg_name

                        # Check, that there are no duplicates
                        pd_funcs_to_append = read_pd_funcs.loc[
                            ~read_pd_funcs.index.isin(self.pd_funcs.index)
                        ]
                        self.pd_funcs = pd.concat([self.pd_funcs, pd_funcs_to_append])
                        pd_params_to_append = read_pd_params.loc[
                            ~read_pd_params.index.isin(self.pd_params.index)
                        ]
                        self.pd_params = pd.concat(
                            [self.pd_params, pd_params_to_append]
                        )

            else:
                missing_files = [key for key in file_dict if file_dict[key] is None]
                logger().warning(
                    f"Files for import of {pkg_name} " f"are missing: {missing_files}"
                )

    def reload_modules(self):
        for pkg_name in self.all_modules:
            for module_name in self.all_modules[pkg_name]:
                module = import_module(module_name)
                try:
                    reload(module)
                # Custom-Modules somehow can't be reloaded
                # because spec is not found
                except ModuleNotFoundError:
                    spec = None
                    if spec:
                        # All errors occuring here will
                        # be caught by the UncaughtHook
                        spec.loader.exec_module(module)
                        sys.modules[module_name] = module


class Controller:
    """New controller, that combines the former old controller and project class and
    loads a controller for each "project".

    The home-path structure should no longer be as rigid as before, just specifying the
    path to meeg- and fsmri-data. For each controller, there is a config-file stored,
    where paths to the meeg-data, the freesurfer-dir and the custom-packages are stored.

    Parameters
    ----------
    config_path : str or Path, optional
        Path to the config-file, if
    meeg_root : str or Path, optional
        Path to the MEEG data root directory, by default None.
    fsmri_root : str or Path, optional
        Path to the FreeSurfer MRI data root directory, by default None.

    Attributes
    ----------
    config_path : str or Path
        Path to the config-file.
    config : dict
        Dictionary containing the configuration data loaded from the config-file.
    """

    def __init__(self, config_path=None, meeg_root=None, fsmri_root=None):
        self._config_path = config_path or QS().value("config_path", defaultValue=None)
        self._config = {}
        self.meeg_root = meeg_root or self.meeg_root
        self.fsmri_root = fsmri_root or self.fsmri_root

        # Property attributes
        self._modules = {}
        self._basic_module_list = ["basic_operations", "basic_plot"]
        self._function_metas = {}
        self._parameter_metas = {}
        self._input_nodes = {k: {} for k in self.input_data_types}
        self._function_nodes = {}

        self.default_settings = {
            "selected_modules": ["basic_operations", "basic_operations"],
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
        }

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
        return self._config

    def save_config(self):
        with open(self._config_path, "w") as file:
            json.dump(self._config, file, indent=4, cls=TypedJSONEncoder)

    @property
    def meeg_root(self):
        return self.config.get("meeg_root", None)

    @meeg_root.setter
    def meeg_root(self, value):
        self.config["meeg_root"] = value
        self.save_config()

    @property
    def fsmri_root(self):
        return self.config.get("fsmri_root", None)

    @fsmri_root.setter
    def fsmri_root(self, value):
        self.config["fsmri_root"] = value
        self.save_config()

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
    def plot_path(self):
        return self.config.get("plots_path", None)

    @plot_path.setter
    def plot_path(self, value):
        if not isdir(value):
            raise ValueError(f"Path {value} does not exist!")

        self._config["plots_path"] = value
        self.save_config()

    @property
    def inputs(self):
        """This holds all data input nodes from MEEG and FSMRI data.

        There can be multiple input-nodes for each data type with each having a distinct
        name (keys in the second level of the dictionary).
        """
        if "inputs" not in self.config:
            self.config["inputs"] = {k: {} for k in self.input_data_types}
        return self.config["inputs"]

    @property
    def input_nodes(self):
        return self._input_nodes

    def input_node(self, data_type, name=None):
        """Get the input node for a specific data type and (group)name."""
        if name is None:
            name = "All"
        if data_type not in self.input_nodes:
            raise ValueError(f"Data type {data_type} not found in inputs.")
        if name not in self.input_nodes[data_type]:
            raise ValueError(f"Group {name} not found in inputs for {data_type}.")
        return self.input_nodes[data_type][name]

    @property
    def selected_inputs(self):
        """This holds all selected inputs."""
        if "selected_inputs" not in self.config:
            self.config["selected_inputs"] = []
        return self.config["selected_inputs"]

    @property
    def input_mapping(self):
        """This holds the mapping of input nodes to data types (like MRI or Empty-
        Room)."""
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
            self.config["parameters"] = {}
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
        if self.parameter_metas is None:
            raise KeyError(f"Parameter '{parameter_name}' not found in Parameter-Meta.")
        default_value = parameter_meta.get("default", None)
        if default_value is None:
            raise KeyError(
                f"Default value for parameter '{parameter_name}' not found in Parameter-Meta."
            )
        return default_value

    def parameter(self, parameter_name, parameter_preset=None, raise_missing=True):
        """Get a specific parameter from the project parameters."""
        parameter_preset = parameter_preset or self.parameter_preset
        if parameter_preset not in self.parameters:
            if raise_missing:
                raise KeyError(
                    f"Parameter preset '{parameter_preset}' not found in project."
                )
            else:
                parameter_preset = list(self.parameters.keys())[0]
        if parameter_name not in self.parameters[parameter_preset]:
            if raise_missing:
                raise KeyError(f"Parameter '{parameter_name}' not found in project.")
            else:
                return self.get_default(parameter_name)

        return self.parameters[parameter_preset][parameter_name]

    @property
    def function_nodes(self):
        """This maps the node(s) to each function used in the project (by name and
        id)."""
        return self._function_nodes

    def function_node(self, function_name, node_id=None):
        """Get the function node for a specific function name and (optional) node id."""
        if function_name not in self.function_nodes:
            raise KeyError(f"Function '{function_name}' not found in project.")
        if node_id is None:
            return self.function_nodes[function_name]
        elif node_id not in self.function_nodes[function_name]:
            raise KeyError(
                f"Node with id '{node_id}' for function '{function_name}' not found."
            )
        return self.function_nodes[function_name][node_id]

    @property
    def function_metas(self):
        """This holds the metadata for the functions used in the project.

        Only unique function names are allowed accross basic and custom packages.
        """
        return self._function_metas

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
        # Get start/end lines of the function code in module
        re.search(code, module_code)

        return None, None, None

    @property
    def modules(self):
        """This holds all modules used in the project."""
        return self._modules

    @property
    def custom_module_meta(self):
        """This holds the custom modules used in the project, stored by name and path to
        the config-file."""
        if "custom_module_meta" not in self.config:
            self.config["custom_module_meta"] = {}
        return self.config["custom_module_meta"]

    @property
    def add_kwargs(self):
        """This holds additional keyword arguments for the project."""
        if "add_kwargs" not in self.config:
            self.config["add_kwargs"] = {}
        return self.config["add_kwargs"]

    def selected_nodes(self):
        """This holds the selected nodes for the project (by id)."""
        if "selected_nodes" not in self.config:
            self.config["selected_nodes"] = []
        return self.config["selected_nodes"]

    @property
    def plot_files(self):
        """This holds the plot file-paths for the project."""
        if "plot_files" not in self.config:
            self.config["plot_files"] = {}
        return self.config["plot_files"]

    @property
    def input_data_types(self):
        """This holds the input data types for the project.

        Keys are the data-type while values are the names/aliases of the data-type
        """
        if "input_data_types" not in self.config:
            self.config["input_data_types"] = {
                "raw": "MEG/EEG",
                "fsmri": "Freesurfer MRI",
            }
            self.save_config()
        return self.config["input_data_types"]

    ####################################################################################
    # Modules
    ####################################################################################
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
            logger().error(f"Module {module_name} not found in {pkg_path}].")
        else:
            self._modules[module_name] = module
        # Load the config file for the basic module
        self._load_module_config(module_name, pkg_path)

    def load_basic_modules(self):
        """Load the basic modules from the basic_functions package."""
        # Add functions to sys.path
        pkg_path = Path(basic_functions.__file__).parent

        for module_name in self._basic_module_list:
            self._import_module(module_name, pkg_path)

    def load_custom_modules(self):
        for module_name, config_file_path in self.custom_module_meta.items():
            pkg_path = Path(config_file_path).parent
            self._import_module(module_name, pkg_path)

    def reload_modules(self):
        """Reload all modules in the controller.

        This method reloads all modules in the controller by removing them from sys.modules
        and importing them again. This ensures that any changes to the module's source code
        are reflected in the controller.

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

        for module_name, module in self.modules.items():
            # Remove the module from sys.modules
            del sys.modules[module_name]

            # Clear bytecode cache if possible
            bytecode_file = cache_from_source(str(module.__file__))
            try:
                os.remove(bytecode_file)
            except Exception as e:
                logger().warning(f"Error clearing bytecode cache: {e}")

            # Import the module again
            new_module = import_module(module_name)
            # Update the module in the controller
            self._modules[module_name] = new_module

    ####################################################################################
    # Node Management
    ####################################################################################
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
        self.meeg_root = pr.data_path
        self.fsmri_root = ct.subjects_dir
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
