"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import json
import logging
import math
import os
import re
import shutil
import subprocess
import sys
import traceback
from ast import literal_eval
from copy import deepcopy
from importlib import resources, import_module, reload
from inspect import getsource
from os import listdir, makedirs
from os.path import isdir, join, isfile, exists, getsize
from pathlib import Path

import mne
import numpy as np
import pandas as pd

from mne_nodes import extra
from mne_nodes.basic_operations import basic_operations
from mne_nodes.basic_plot import basic_plot
from mne_nodes.gui.gui_utils import get_user_input
from mne_nodes.pipeline.loading import MEEG, FSMRI, Group
from mne_nodes.pipeline.pipeline_utils import count_dict_keys
from mne_nodes.pipeline.io import encode_tuples, TypedJSONEncoder, type_json_hook
from mne_nodes.pipeline.settings import Settings

renamed_parameters = {
    "filter_target": {"Raw": "raw", "Epochs": "epochs", "Evoked": "evoked"},
    "bad_interpolation": {
        "Raw (Filtered)": "raw_filtered",
        "Epochs": "epochs",
        "Evoked": "evoked",
    },
    "ica_fitto": {
        "Raw (Unfiltered)": "raw",
        "Raw (Filtered)": "raw_filtered",
        "Epochs": "epochs",
    },
    "noise_cov_mode": {"Empty-Room": "erm", "Epochs": "epochs"},
    "ica_source_data": {
        "Raw (Unfiltered)": "raw",
        "Raw (Filtered)": "raw_filtered",
        "Epochs": "epochs",
        "Epochs (EOG)": "epochs_eog",
        "Epochs (ECG)": "epochs_ecg",
        "Evokeds": "evoked",
        "Evokeds (EOG)": "evoked (EOG)",
        "Evokeds (ECG)": "evoked (ECG)",
    },
    "ica_overlay_data": {
        "Raw (Unfiltered)": "raw",
        "Raw (Filtered)": "raw_filtered",
        "Evokeds": "evoked",
        "Evokeds (EOG)": "evoked (EOG)",
        "Evokeds (ECG)": "evoked (ECG)",
    },
}

# New packages with {import_name: install_name} (can be the same)
new_packages = {"darkdetect": "darkdetect"}


def install_package(package_name):
    print(f"Installing {package_name}...")
    print(
        subprocess.check_output(
            [sys.executable, "-m", "pip", "install", package_name], text=True
        )
    )


def uninstall_package(package_name):
    print(f"Uninstalling {package_name}...")
    print(
        subprocess.check_output(
            [sys.executable, "-m", "pip", "uninstall", "-y", package_name], text=True
        )
    )


def legacy_import_check(test_package=None):
    """This function checks for recent package changes and offers installation
    or manual installation instructions."""
    # For testing purposes
    if test_package is not None:
        new_packages[test_package] = test_package

    for import_name, install_name in new_packages.items():
        try:
            __import__(import_name)
        except ImportError:
            print(f"The package {import_name} is required for this application.\n")
            ans = input("Do you want to install the new package now? [y/n]").lower()
            if ans == "y":
                try:
                    install_package(install_name)
                except subprocess.CalledProcessError:
                    logging.critical("Installation failed!")
                else:
                    return
            print(
                f"Please install the new package {import_name} "
                f"manually with:\n\n"
                f"> pip install {install_name}"
            )
            sys.exit(1)


def transfer_file_params_to_single_subject(ct):
    old_fp_path = join(ct.pr.pscripts_path, f"file_parameters_{ct.pr.name}.json")
    if isfile(old_fp_path):
        print("Transfering File-Parameters to single files...")
        with open(old_fp_path) as file:
            file_parameters = json.load(file, object_hook=type_json_hook)
            for obj_name in file_parameters:
                if obj_name in ct.pr.all_meeg:
                    obj = MEEG(obj_name, ct)
                elif obj_name in ct.pr.all_fsmri:
                    obj = FSMRI(obj_name, ct)
                elif obj_name in ct.pr.all_groups:
                    obj = Group(obj_name, ct)
                else:
                    obj = None
                if obj is not None:
                    if not isdir(obj.save_dir):
                        continue
                    obj.file_parameters = file_parameters[obj_name]
                    obj.save_file_parameter_file()
                    obj.clean_file_parameters()
        os.remove(old_fp_path)
        print("Done!")


def convert_pandas_meta(func_pd, param_pd):
    """Convert pandas DataFrames to a dictionary structure for function and
    parameter configuration."""
    modules = func_pd["module"].unique()
    input_names = ["meeg", "fsmri", "group"]
    configs = {}
    for module_name in modules:
        module = basic_operations if module_name == "operations" else basic_plot
        module_dict = {
            "module_name": module_name,
            "module_alias": module_name,
            "functions": {},
            "parameters": {},
        }
        param_set = set()

        for func_name, row in func_pd[func_pd["module"] == module_name].iterrows():
            row_dict = row.to_dict()
            if row_dict["mayavi"]:
                row_dict["thread-safe"] = False
            else:
                row_dict["thread-safe"] = True
            if row_dict["matplotlib"] or row_dict["mayavi"]:
                row_dict["plot"] = True
            else:
                row_dict["plot"] = False

            for pop_key in [
                "matplotlib",
                "mayavi",
                "target",
                "tab",
                "dependencies",
                "pkg_name",
            ]:
                row_dict.pop(pop_key)

            params = row_dict.pop("func_args").split(",")

            # Get inputs/outputs and parameters
            input = params.pop(0)
            func = getattr(module, func_name)
            code = getsource(func)
            row_dict["inputs"] = re.findall(rf"{input}\.load_([a-z_]+)\(", code)
            row_dict["outputs"] = re.findall(rf"{input}\.save_([a-z_]+)\(", code)
            row_dict["parameters"] = [p for p in params if p not in input_names]

            for key, value in row_dict.items():
                if isinstance(value, float) and math.isnan(value):
                    row_dict[key] = None

            module_dict["functions"][func_name] = row_dict
            param_set.update(params)

        for param_name, row in param_pd.iterrows():
            if param_name not in param_set:
                continue
            row_dict = row.to_dict()
            eval_dict = {}
            for key, value in row_dict.items():
                if key in ["default", "gui_args"]:
                    try:
                        value = literal_eval(value)
                    except (ValueError, SyntaxError):
                        pass
                # Rename gui_type to gui
                if key == "gui_type":
                    key = "gui"
                # Convert None values from NaN
                if isinstance(value, float) and math.isnan(value):
                    value = None
                eval_dict[key] = value
            eval_dict.pop("group")
            # Convert gui-args
            gui_args = eval_dict.pop("gui_args", {})
            if gui_args is not None:
                for k, v in gui_args.items():
                    eval_dict[k] = v
            # Convert tuple types
            if param_name in [
                "t_epoch",
                "baseline",
                "stc_animation_span",
                "con_time_window",
            ]:
                eval_dict["default"] = tuple(eval_dict["default"])

            module_dict["parameters"][param_name] = eval_dict
        configs[module_name] = module_dict

    return configs


home_dirs = ["custom_packages", "freesurfer", "projects"]
project_dirs = ["_pipeline_scripts", "data", "figures"]


class OldController:
    def __init__(self, home_path=None, selected_project=None, edu_program_name=None):
        # Check Home-Path
        self.pr = None
        # Try to load home_path from QSettings
        self.home_path = home_path or Settings().value("home_path", defaultValue=None)
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
        logger = logging.getLogger()
        logging_path = Settings.value("log_file_path") or join(
            Path.home() / "mne_nodes.log"
        )
        file_handler = logging.FileHandler(logging_path, "w")
        file_handler.set_name("file")
        logger.addHandler(file_handler)

        logging.info(f"Home-Path: {self.home_path}")
        Settings().setValue("home_path", self.home_path)
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
        Settings().sync()
        qs_keys = set(Settings().childKeys())
        qdefault_keys = set(self.default_settings["qsettings"])
        # Remove additional (old) keys not appearing in default-settings
        for qsetting in qs_keys - qdefault_keys:
            Settings().remove(qsetting)
        # Add new keys from default-settings which are not present in QSettings
        for qsetting in qdefault_keys - qs_keys:
            Settings().setValue(qsetting, self.default_settings["qsettings"][qsetting])

    def save_settings(self):
        try:
            with open(join(self.home_path, "mne_nodes-settings.json"), "w") as file:
                json.dump(self.settings, file, indent=4)
        except FileNotFoundError:
            logging.warning("Settings could not be saved!")

        # Sync QSettings with other instances
        Settings().sync()

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
        logging.info(f"Selected-Project: {self.pr.name}")
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
            logging.warning(
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
                    logging.critical(
                        f"Can't rename {old_name} to {new_project_name}. "
                        f"Probably a file from inside the project is still opened. "
                        f"Please close all files and try again."
                    )
                else:
                    self.projects.remove(old_name)
                    self.projects.append(new_project_name)
        else:
            logging.warning(
                "The project-folder seems to be not writable at the moment, "
                "maybe some files inside are still in use?"
            )

    def copy_parameters_between_projects(
        self, from_name, from_p_preset, to_name, to_p_preset, parameter=None
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
                self.pr.project_path, f"_pipeline_scripts{self.edu_program['name']}"
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
        sys.path.insert(0, str(Path(basic_operations.__file__).parent))
        basic_functions_list = [x for x in dir(basic_operations) if "__" not in x]
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
                logging.warning(
                    f"Files for import of {pkg_name} are missing: {missing_files}"
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


class Project:
    """A class with attributes for all the paths, file-lists/dicts and
    parameters of the selected project."""

    def __init__(self, controller, name):
        self.ct = controller
        self.name = name

        self.init_main_paths()
        self.init_attributes()
        self.init_pipeline_scripts()
        self.load()
        self.save()
        # ToDo: MacOs weird folders added (.DSStore)
        # self.check_data()

    def init_main_paths(self):
        # Main folder of project
        self.project_path = join(self.ct.projects_path, self.name)
        # Folder to store the data
        self.data_path = join(self.project_path, "data")
        # Folder to store the figures (with an additional subfolder
        # for each parameter-preset)
        self.figures_path = join(self.project_path, "figures")
        # A dedicated folder to store grand-average data
        self.save_dir_averages = join(self.data_path, "grand_averages")
        # A folder to store all pipeline-scripts as .json-files
        self.pscripts_path = join(self.project_path, "_pipeline_scripts")

        self.main_paths = [
            self.ct.subjects_dir,
            self.data_path,
            self.save_dir_averages,
            self.pscripts_path,
            self.ct.custom_pkg_path,
            self.figures_path,
        ]

        # Create or check existence of main_paths
        for path in self.main_paths:
            if not exists(path):
                makedirs(path)
                logging.debug(f"{path} created")

    def init_attributes(self):
        # Stores the names of all MEG/EEG-Files
        self.all_meeg = []
        # Stores selected MEG/EEG-Files
        self.sel_meeg = []
        # Stores Bad-Channels for each MEG/EEG-File
        self.meeg_bad_channels = {}
        # Stores Event-ID for each MEG/EEG-File
        self.meeg_event_id = {}
        # Stores selected event-id-labels
        self.sel_event_id = {}
        # Stores the names of all Empty-Room-Files (MEG/EEG)
        self.all_erm = []
        # Maps each MEG/EEG-File to a Empty-Room-File or None
        self.meeg_to_erm = {}
        # Stores the names of all Freesurfer-Segmentation-Folders
        # in Subjects-Dir
        self.all_fsmri = []
        # Stores selected Freesurfer-Segmentations
        self.sel_fsmri = []
        # Maps each MEG/EEG-File to a Freesurfer-Segmentation or None
        self.meeg_to_fsmri = {}
        # Stores the ICA-Components to be excluded
        self.meeg_ica_exclude = {}
        # Groups MEG/EEG-Files e.g. for Grand-Average
        self.all_groups = {}
        # Stores selected Grand-Average-Groups
        self.sel_groups = []
        # Stores paths of saved plots
        self.plot_files = {}
        # Stores functions and if they are selected
        self.sel_functions = []
        # Stores additional keyword-arguments for functions by function-name
        self.add_kwargs = {}
        # Stores parameters for each Parameter-Preset
        self.parameters = {}
        # Parameter-Preset
        self.p_preset = "Default"

        # Attributes, which have their own special function for loading
        self.special_loads = ["parameters", "p_preset"]

    def init_pipeline_scripts(self):
        # ToDo: Transition scripts to toml (only keep parameters as json for types)
        # Initiate Project-Lists and Dicts
        self.all_meeg_path = join(self.pscripts_path, f"all_meeg_{self.name}.json")
        self.sel_meeg_path = join(self.pscripts_path, f"selected_meeg_{self.name}.json")
        self.meeg_bad_channels_path = join(
            self.pscripts_path, f"meeg_bad_channels_{self.name}.json"
        )
        self.meeg_event_id_path = join(
            self.pscripts_path, f"meeg_event_id_{self.name}.json"
        )
        self.sel_event_id_path = join(
            self.pscripts_path, f"selected_event_ids_{self.name}.json"
        )
        self.all_erm_path = join(self.pscripts_path, f"all_erm_{self.name}.json")
        self.meeg_to_erm_path = join(
            self.pscripts_path, f"meeg_to_erm_{self.name}.json"
        )
        self.all_fsmri_path = join(self.pscripts_path, f"all_fsmri_{self.name}.json")
        self.sel_fsmri_path = join(
            self.pscripts_path, f"selected_fsmri_{self.name}.json"
        )
        self.meeg_to_fsmri_path = join(
            self.pscripts_path, f"meeg_to_fsmri_{self.name}.json"
        )
        self.ica_exclude_path = join(
            self.pscripts_path, f"ica_exclude_{self.name}.json"
        )
        self.all_groups_path = join(self.pscripts_path, f"all_groups_{self.name}.json")
        self.sel_groups_path = join(
            self.pscripts_path, f"selected_groups_{self.name}.json"
        )
        self.plot_files_path = join(self.pscripts_path, f"plot_files_{self.name}.json")
        self.sel_functions_path = join(
            self.pscripts_path, f"selected_functions_{self.name}.json"
        )
        self.add_kwargs_path = join(
            self.pscripts_path, f"additional_kwargs_{self.name}.json"
        )
        self.parameters_path = join(self.pscripts_path, f"parameters_{self.name}.json")
        self.sel_p_preset_path = join(
            self.pscripts_path, f"sel_p_preset_{self.name}.json"
        )

        # Map the paths to their attribute in the Project-Class
        self.path_to_attribute = {
            self.all_meeg_path: "all_meeg",
            self.sel_meeg_path: "sel_meeg",
            self.meeg_bad_channels_path: "meeg_bad_channels",
            self.meeg_event_id_path: "meeg_event_id",
            self.sel_event_id_path: "sel_event_id",
            self.all_erm_path: "all_erm",
            self.meeg_to_erm_path: "meeg_to_erm",
            self.all_fsmri_path: "all_fsmri",
            self.sel_fsmri_path: "sel_fsmri",
            self.meeg_to_fsmri_path: "meeg_to_fsmri",
            self.ica_exclude_path: "meeg_ica_exclude",
            self.all_groups_path: "all_groups",
            self.sel_groups_path: "sel_groups",
            self.plot_files_path: "plot_files",
            self.sel_functions_path: "sel_functions",
            self.add_kwargs_path: "add_kwargs",
            self.parameters_path: "parameters",
            self.sel_p_preset_path: "p_preset",
        }

    def rename(self, new_name):
        # Rename folder
        old_name = self.name
        os.rename(self.project_path, join(self.ct.projects_path, new_name))
        self.name = new_name
        self.init_main_paths()
        # Rename project-files
        old_paths = [Path(p).name for p in self.path_to_attribute]
        self.init_pipeline_scripts()
        new_paths = [Path(p).name for p in self.path_to_attribute]
        for old_path, new_path in zip(old_paths, new_paths):
            os.rename(
                join(self.pscripts_path, old_path), join(self.pscripts_path, new_path)
            )
            logging.info(f"Renamed project-script {old_path} to {new_path}")
        logging.info(f'Finished renaming project "{old_name}" to "{new_name}"')

    def load_lists(self):
        # Old Paths to allow transition (22.11.2020)
        self.old_all_meeg_path = join(self.pscripts_path, "file_list.json")
        self.old_sel_meeg_path = join(self.pscripts_path, "selected_files.json")
        self.old_meeg_bad_channels_path = join(
            self.pscripts_path, "bad_channels_dict.json"
        )
        self.old_meeg_event_id_path = join(self.pscripts_path, "event_id_dict.json")
        self.old_sel_event_id_path = join(
            self.pscripts_path, "selected_evid_labels.json"
        )
        self.old_all_erm_path = join(self.pscripts_path, "erm_list.json")
        self.old_meeg_to_erm_path = join(self.pscripts_path, "erm_dict.json")
        self.old_all_fsmri_path = join(self.pscripts_path, "mri_sub_list.json")
        self.old_sel_fsmri_path = join(self.pscripts_path, "selected_mri_files.json")
        self.old_meeg_to_fsmri_path = join(self.pscripts_path, "sub_dict.json")
        self.old_all_groups_path = join(self.pscripts_path, "grand_avg_dict.json")
        self.old_sel_groups_path = join(
            self.pscripts_path, "selected_grand_average_groups.json"
        )
        self.old_sel_funcs_path = join(self.pscripts_path, "selected_funcs.json")

        # Old Paths to allow transition (22.11.2020)
        self.old_paths = {
            self.all_meeg_path: self.old_all_meeg_path,
            self.sel_meeg_path: self.old_sel_meeg_path,
            self.meeg_bad_channels_path: self.old_meeg_bad_channels_path,
            self.meeg_event_id_path: self.old_meeg_event_id_path,
            self.sel_event_id_path: self.old_sel_event_id_path,
            self.all_erm_path: self.old_all_erm_path,
            self.meeg_to_erm_path: self.old_meeg_to_erm_path,
            self.all_fsmri_path: self.old_all_fsmri_path,
            self.sel_fsmri_path: self.old_sel_fsmri_path,
            self.meeg_to_fsmri_path: self.old_meeg_to_fsmri_path,
            self.all_groups_path: self.old_all_groups_path,
            self.sel_groups_path: self.old_sel_groups_path,
            self.sel_functions_path: self.old_sel_funcs_path,
        }

        for path in [
            p
            for p in self.path_to_attribute
            if self.path_to_attribute[p] not in self.special_loads
        ]:
            attribute_name = self.path_to_attribute[path]
            try:
                with open(path) as file:
                    loaded_attribute = json.load(file, object_hook=type_json_hook)
                    # Make sure, that loaded object has same type
                    # as default from __init__
                    if isinstance(
                        loaded_attribute, type(getattr(self, attribute_name))
                    ):
                        setattr(self, attribute_name, loaded_attribute)
            # Either empty file or no file, leaving default from __init__
            except (json.JSONDecodeError, FileNotFoundError):
                # Old Paths to allow transition (22.11.2020)
                try:
                    with open(self.old_paths[path]) as file:
                        setattr(
                            self,
                            attribute_name,
                            json.load(file, object_hook=type_json_hook),
                        )
                except (json.JSONDecodeError, FileNotFoundError, KeyError):
                    pass

    def load_parameters(self):
        try:
            with open(
                join(self.pscripts_path, f"parameters_{self.name}.json")
            ) as read_file:
                loaded_parameters = json.load(read_file, object_hook=type_json_hook)

                for p_preset in loaded_parameters:
                    # Make sure, that only parameters,
                    # which exist in pd_params are loaded
                    for param in [
                        p
                        for p in loaded_parameters[p_preset]
                        if p not in self.ct.pd_params.index
                    ]:
                        if "_exp" not in param:
                            loaded_parameters[p_preset].pop(param)

                    # Add parameters, which exist in extra/parameters.csv,
                    # but not in loaded-parameters
                    # (e.g. added with custom-module)
                    for param in [
                        p
                        for p in self.ct.pd_params.index
                        if p not in loaded_parameters[p_preset]
                    ]:
                        try:
                            eval_param = literal_eval(
                                self.ct.pd_params.loc[param, "default"]
                            )
                        except (ValueError, SyntaxError, NameError):
                            # Allow parameters to be defined by functions
                            # e.g. by numpy, etc.
                            is_func_gui = (
                                self.ct.pd_params.loc[param, "gui_type"] == "FuncGui"
                            )
                            if is_func_gui:
                                default_string = self.ct.pd_params.loc[param, "default"]
                                eval_param = eval(default_string, {"np": np})
                                exp_name = param + "_exp"
                                loaded_parameters[p_preset].update(
                                    {exp_name: default_string}
                                )
                            else:
                                eval_param = self.ct.pd_params.loc[param, "default"]
                        loaded_parameters[p_preset].update({param: eval_param})
                    # Change renamed legacy parameters
                    for param, value in loaded_parameters[p_preset].items():
                        if param in renamed_parameters:
                            if value in renamed_parameters[param]:
                                loaded_parameters[p_preset][param] = renamed_parameters[
                                    param
                                ][value]

                self.parameters = loaded_parameters
        except (FileNotFoundError, json.decoder.JSONDecodeError):
            self.load_default_parameters()

    def load_default_param(self, param_name):
        string_param = self.ct.pd_params.loc[param_name, "default"]
        try:
            self.parameters[self.p_preset][param_name] = literal_eval(string_param)
        except (ValueError, SyntaxError):
            # Allow parameters to be defined by functions e.g. by numpy, etc.
            if self.ct.pd_params.loc[param_name, "gui_type"] == "FuncGui":
                self.parameters[self.p_preset][param_name] = eval(
                    string_param, {"np": np}
                )
                exp_name = param_name + "_exp"
                self.parameters[self.p_preset][exp_name] = string_param
            else:
                self.parameters[self.p_preset][param_name] = string_param

    def load_default_parameters(self):
        # Empty the dict for current Parameter-Preset
        self.parameters[self.p_preset] = {}
        for param_name in self.ct.pd_params.index:
            self.load_default_param(param_name)

    def load_last_p_preset(self):
        try:
            with open(self.sel_p_preset_path) as read_file:
                self.p_preset = json.load(read_file)
                # If parameter-preset not in Parameters,
                # load first Parameter-Key(=Parameter-Preset)
                if self.p_preset not in self.parameters:
                    self.p_preset = list(self.parameters.keys())[0]
        except (FileNotFoundError, json.decoder.JSONDecodeError):
            self.p_preset = list(self.parameters.keys())[0]

    def load(self):
        self.load_lists()
        self.load_parameters()
        self.load_last_p_preset()

    def save(self, worker_signals=None):
        if worker_signals:
            worker_signals.pgbar_max.emit(len(self.path_to_attribute))

        for idx, path in enumerate(self.path_to_attribute):
            if worker_signals:
                worker_signals.pgbar_n.emit(idx)
                worker_signals.pgbar_text.emit(f"Saving {self.path_to_attribute[path]}")

            attribute = getattr(self, self.path_to_attribute[path], None)

            # Make sure the tuples are encoded correctly
            if isinstance(attribute, dict):
                attribute = deepcopy(attribute)
                encode_tuples(attribute)

            try:
                with open(path, "w") as file:
                    json.dump(attribute, file, cls=TypedJSONEncoder, indent=4)

            except json.JSONDecodeError as err:
                logging.warning(f"There is a problem with path:\n{err}")

    def add_meeg(self, name, file_path=None, is_erm=False):
        if is_erm:
            # Organize Empty-Room-Files
            if name not in self.all_erm:
                self.all_erm.append(name)
        else:
            # Organize other files
            if name not in self.all_meeg:
                self.all_meeg.append(name)

        # Copy sub_files to destination (with MEEG-Class
        # to also include raw into file_parameters)
        meeg = MEEG(name, self.ct)

        if file_path is not None:
            # Get bad-channels from raw-file
            raw = mne.io.read_raw(file_path, preload=True)
            loaded_bads = raw.info["bads"]
            if len(loaded_bads) > 0:
                self.meeg_bad_channels[name] = raw.info["bads"]

            meeg.save_raw(raw)

        return meeg

    def remove_meeg(self, remove_files):
        for meeg in self.sel_meeg:
            try:
                # Remove MEEG from Lists/Dictionaries
                self.all_meeg.remove(meeg)
            except ValueError:
                logging.warning(f"{meeg} already removed!")
            self.meeg_to_erm.pop(meeg, None)
            self.meeg_to_fsmri.pop(meeg, None)
            self.meeg_bad_channels.pop(meeg, None)
            self.meeg_event_id.pop(meeg, None)
            if remove_files:
                try:
                    remove_path = join(self.data_path, meeg)
                    shutil.rmtree(remove_path)
                    logging.info(f"Succesful removed {remove_path}")
                except FileNotFoundError:
                    logging.critical(join(self.data_path, meeg) + " not found!")
        self.sel_meeg.clear()

    def add_fsmri(self, name, src_dir=None):
        self.all_fsmri.append(name)
        # Initialize FSMRI
        fsmri = FSMRI(name, self.ct)
        if src_dir is not None:
            dst_dir = join(self.ct.subjects_dir, name)
            if not isdir(dst_dir):
                logging.debug(f"Copying Folder from {src_dir}...")
                try:
                    shutil.copytree(src_dir, dst_dir)
                # surfaces with .H and .K at the end can't be copied
                except shutil.Error:
                    pass
                logging.debug(f"Finished Copying to {dst_dir}")
            else:
                logging.info(f"{dst_dir} already exists")

        return fsmri

    def remove_fsmri(self, remove_files):
        for fsmri in self.sel_fsmri:
            try:
                self.all_fsmri.remove(fsmri)
            except ValueError:
                logging.warning(f"{fsmri} already deleted!")
            if remove_files:
                try:
                    shutil.rmtree(join(self.ct.subjects_dir, fsmri))
                except FileNotFoundError:
                    logging.info(join(self.ct.subjects_dir, fsmri) + " not found!")
        self.sel_fsmri.clear()

    def add_group(self):
        pass

    def remove_group(self):
        pass

    def check_data(self):
        missing_objects = [
            x
            for x in listdir(self.data_path)
            if x != "grand_averages"
            and x not in self.all_meeg
            and x not in self.all_erm
        ]

        for obj in missing_objects:
            self.all_meeg.append(obj)

        # Get Freesurfer-folders (with 'surf'-folder)
        # from subjects_dir (excluding .files for Mac)
        read_dir = sorted(
            [f for f in os.listdir(self.ct.subjects_dir) if not f.startswith(".")],
            key=str.lower,
        )
        self.all_fsmri = [
            fsmri
            for fsmri in read_dir
            if exists(join(self.ct.subjects_dir, fsmri, "surf"))
        ]

        self.save()

    def clean_file_parameters(self, worker_signals=None):
        if worker_signals is not None:
            worker_signals.pgbar_max.emit(
                len(self.all_meeg) + len(self.all_fsmri) + len(self.all_groups.keys())
            )
        count = 0

        for meeg in self.all_meeg:
            meeg = MEEG(meeg, self.ct)
            worker_signals.pgbar_text.emit(f"Cleaning File-Parameters for {meeg}")
            meeg.clean_file_parameters()
            count += 1
            if worker_signals is not None:
                worker_signals.pgbar_n.emit(count)
                if worker_signals.was_canceled:
                    logging.info("Cleaning was canceled by the user!")
                    return

        for fsmri in self.all_fsmri:
            fsmri = FSMRI(fsmri, self.ct)
            worker_signals.pgbar_text.emit(f"Cleaning File-Parameters for {fsmri}")
            fsmri.clean_file_parameters()
            count += 1
            if worker_signals is not None:
                worker_signals.pgbar_n.emit(count)
                if worker_signals.was_canceled:
                    logging.info("Cleaning was canceled by the user!")
                    return

        for group in self.all_groups:
            group = Group(group, self.ct)
            worker_signals.pgbar_text.emit(f"Cleaning File-Parameters for {group}")
            group.clean_file_parameters()
            count += 1
            if worker_signals is not None:
                worker_signals.pgbar_n.emit(count)
                if worker_signals.was_canceled:
                    logging.info("Cleaning was canceled by the user!")
                    return

    def clean_plot_files(self, worker_signals=None):
        all_image_paths = []
        # Remove object-keys which no longer exist
        remove_obj = []
        n_remove_ppreset = 0
        n_remove_funcs = 0

        if worker_signals is not None:
            worker_signals.pgbar_max.emit(count_dict_keys(self.plot_files, max_level=3))
        key_count = 0

        for obj_key in self.plot_files:
            key_count += 1
            if worker_signals is not None:
                worker_signals.pgbar_n.emit(key_count)

            if obj_key not in self.all_meeg + self.all_erm + self.all_fsmri + list(
                self.all_groups.keys()
            ):
                remove_obj.append(obj_key)
            else:
                # Remove Parameter-Presets which no longer exist
                remove_p_preset = []
                for p_preset in self.plot_files[obj_key]:
                    key_count += 1
                    if worker_signals is not None:
                        worker_signals.pgbar_n.emit(key_count)

                    if p_preset not in self.parameters.keys():
                        key_count += len(self.plot_files[obj_key][p_preset])
                        if worker_signals is not None:
                            worker_signals.pgbar_n.emit(key_count)

                        remove_p_preset.append(p_preset)
                    else:
                        # Remove funcs which no longer exist
                        # or got no paths left
                        remove_funcs = []
                        for func in self.plot_files[obj_key][p_preset]:
                            key_count += 1
                            if worker_signals is not None:
                                worker_signals.pgbar_n.emit(key_count)

                            # Cancel if canceled
                            if (
                                worker_signals is not None
                                and worker_signals.was_canceled
                            ):
                                logging.info("Cleaning was canceled by user")
                                return

                            if func not in self.ct.pd_funcs.index:
                                remove_funcs.append(func)
                            else:
                                # Remove image-paths which no longer exist
                                for rel_image_path in self.plot_files[obj_key][
                                    p_preset
                                ][func]:
                                    image_path = Path(
                                        join(self.figures_path, rel_image_path)
                                    )
                                    if (
                                        not isfile(image_path)
                                        or self.figures_path in rel_image_path
                                    ):
                                        self.plot_files[obj_key][p_preset][func].remove(
                                            rel_image_path
                                        )
                                    else:
                                        all_image_paths.append(str(image_path))
                                if len(self.plot_files[obj_key][p_preset][func]) == 0:
                                    # Keys can't be dropped from dictionary
                                    # during iteration
                                    remove_funcs.append(func)

                        for remove_func_key in remove_funcs:
                            self.plot_files[obj_key][p_preset].pop(remove_func_key)
                        n_remove_funcs += len(remove_funcs)

                for remove_preset_key in remove_p_preset:
                    self.plot_files[obj_key].pop(remove_preset_key)
                n_remove_ppreset += len(remove_p_preset)

            logging.info(
                f"Removed {n_remove_ppreset} Parameter-Presets and "
                f"{n_remove_funcs} from {obj_key}"
            )

        for remove_key in remove_obj:
            self.plot_files.pop(remove_key)
        logging.info(f"Removed {len(remove_obj)} Objects from Plot-Files")

        # Remove image-files, which aren't listed in plot_files.
        free_space = 0
        logging.info("Removing unregistered images...")
        n_removed_images = 0
        for root, _, files in os.walk(self.figures_path):
            files = [join(root, f) for f in files]
            for file_path in [
                fp for fp in files if str(Path(fp)) not in all_image_paths
            ]:
                free_space += getsize(file_path)
                n_removed_images += 1
                os.remove(file_path)
        logging.info(f"Removed {n_removed_images} images")

        # Remove empty folders (loop until all empty folders are removed)
        logging.info("Removing empty folders...")
        n_removed_folders = 0
        folder_loop = True
        # Redo the file-walk because folders can get empty
        # by deleting folders inside
        while folder_loop:
            folder_loop = False
            for root, folders, _ in os.walk(self.figures_path):
                folders = [join(root, fd) for fd in folders]
                for folder in [fdp for fdp in folders if len(listdir(fdp)) == 0]:
                    os.rmdir(folder)
                    n_removed_folders += 1
                    folder_loop = True
        logging.info(f"Removed {n_removed_folders} folders")

        logging.info(f"{round(free_space / (1024**2), 2)} MB of space was freed!")
