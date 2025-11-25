"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import inspect
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
from functools import partial
from importlib import resources, import_module, reload
from inspect import getsource
from os import listdir, makedirs
from os.path import isdir, join, isfile, exists, getsize
from pathlib import Path

import mne
import numpy as np
import pandas as pd
from qtpy import compat
from qtpy.QtCore import Signal, QSize
from qtpy.QtGui import QAction, QFont, QTextDocument
from qtpy.QtWidgets import (
    QMainWindow,
    QMessageBox,
    QApplication,
    QLabel,
    QComboBox,
    QPushButton,
    QWidget,
    QGridLayout,
    QTabWidget,
    QScrollArea,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QSizePolicy,
    QDialog,
    QListView,
    QProgressBar,
    QCheckBox,
    QFormLayout,
    QLineEdit,
    QButtonGroup,
)

from mne_nodes import extra, _widgets, ismac, iswin
from mne_nodes.basic_operations import basic_operations
from mne_nodes.basic_plot import basic_plot
from mne_nodes.gui import parameter_widgets
from mne_nodes.gui.base_widgets import (
    SimpleDialog,
    SimpleList,
    CheckList,
    CheckDictList,
    EditDict,
)
from mne_nodes.gui.code_editor import CodeEditor
from mne_nodes.gui.console import MainConsoleWidget
from mne_nodes.gui.dialogs import (
    RemoveProjectsDlg,
    RawInfo,
    QuickGuide,
    AboutDialog,
    SysInfoMsg,
)
from mne_nodes.gui.education_widgets import EducationTour, EducationEditor
from mne_nodes.gui.function_widgets import (
    SelectDependencies,
    EditGuiArgsDlg,
    ChooseOptions,
    ImportFuncs,
    TestParamGui,
    SavePkgDialog,
)
from mne_nodes.gui.gui_utils import (
    get_user_input,
    set_ratio_geometry,
    center,
    ColorTester,
    get_std_icon,
    set_app_theme,
)
from mne_nodes.gui.loading_widgets import (
    AddFilesDialog,
    ReloadRaw,
    AddMRIDialog,
    FileManagment,
    ExportDialog,
    SubjectWizard,
    FileDictDialog,
    SubBadsDialog,
    EventIDGui,
    ICASelect,
    CopyTrans,
    FileDock,
)
from mne_nodes.gui.models import RunModel, CustomFunctionModel
from mne_nodes.gui.node.node_viewer import NodeViewer
from mne_nodes.gui.parameter_widgets import SettingsDlg, IntGui, BoolGui, ParametersDock
from mne_nodes.gui.plot_widgets import PlotViewSelection
from mne_nodes.gui.tools import DataTerminal
from mne_nodes.pipeline.controller import Controller
from mne_nodes.pipeline.execution import WorkerDialog, QProcessDialog
from mne_nodes.pipeline.function_utils import close_all, QRunController
from mne_nodes.pipeline.io import encode_tuples, TypedJSONEncoder, type_json_hook
from mne_nodes.pipeline.loading import MEEG, FSMRI, Group
from mne_nodes.pipeline.pipeline_utils import (
    count_dict_keys,
    restart_program,
    _run_from_script,
)
from mne_nodes.pipeline.settings import Settings

# Add compatibility enums for Qt5/Qt6 differences
from mne_nodes.qt_compat import (
    CMBX_ADJUST_CONTENTS,
    RIGHT_DOCK,
    MB_YES,
    MB_NO,
    MB_CANCEL,
    ALIGN_LEFT,
    ALIGN_TOP,
    ALIGN_CENTER,
    LEFT_DOCK,
    ALIGN_HCENTER,
)

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


def check_none(value):
    """Check if a value is None or NaN and return None."""
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    if isinstance(value, list) and len(value) == 0:
        return True
    if isinstance(value, dict) and len(value) == 0:
        return True
    if isinstance(value, tuple) and len(value) == 0:
        return True
    if isinstance(value, set) and len(value) == 0:
        return True
    if isinstance(value, Path) and not value.exists():
        return True
    if isinstance(value, np.ndarray) and value.size == 0:
        return True
    return False


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
            if func_name == "plot_grand_avg_connect":
                pass
            if check_none(row_dict["alias"]):
                row_dict.pop("alias")

            # Get inputs/outputs and parameters
            params = row_dict.pop("func_args").split(",")
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
            # Make sure alias, unit and description are removed when None
            for key in ["alias", "unit", "description", "gui_args"]:
                if check_none(row_dict[key]):
                    row_dict.pop(key)
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
                    # Remove deprecated type_selection kwarg for MultiTypeGui
                    if k == "type_selection":
                        continue
                    eval_dict[k] = v
            # Convert tuple types
            if param_name in [
                "t_epoch",
                "baseline",
                "stc_animation_span",
                "con_time_window",
            ]:
                eval_dict["default"] = tuple(eval_dict["default"])

            # Convert options to list if it's a dict
            if "options" in eval_dict:
                if isinstance(eval_dict["options"], dict):
                    eval_dict["options"] = [k for k in eval_dict["options"]]

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
        self.home_path = home_path or Settings().get("home_path", default=None)
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
        logging_path = Settings.get("log_file_path") or join(
            Path.home() / "mne_nodes.log"
        )
        file_handler = logging.FileHandler(logging_path, "w")
        file_handler.set_name("file")
        logger.addHandler(file_handler)

        logging.info(f"Home-Path: {self.home_path}")
        Settings().set("home_path", self.home_path)
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
            selected_project = self.settings.get("selected_project")

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
        qs_keys = set(Settings().keys())
        qdefault_keys = set(self.default_settings["qsettings"])
        # Remove additional (old) keys not appearing in default-settings
        for qsetting in qs_keys - qdefault_keys:
            Settings().remove(qsetting)
        # Add new keys from default-settings which are not present in QSettings
        for qsetting in qdefault_keys - qs_keys:
            Settings().set(qsetting, self.default_settings["qsettings"][qsetting])

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
                        except (ValueError, SyntaxError):
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


class OldMainWindow(QMainWindow):
    # Define Main-Window-Signals to send into QThread
    # to control function execution
    cancel_functions = Signal(bool)
    plot_running = Signal(bool)

    def __init__(self, controller):
        super().__init__()
        _widgets["main_window"] = self
        self.setWindowTitle("MNE-Pipeline HD")

        # Set QThread as default
        Settings().set("use_qthread", True)

        # Initiate attributes for Main-Window
        self.ct = controller
        self.pr = controller.pr
        self.edu_tour = None
        self.bt_dict = {}
        # For functions, which should or should not
        # be called durin initialization
        self.first_init = True
        # True, if Pipeline is running (to avoid parallel starts of RunDialog)
        self.pipeline_running = False
        # For the closeEvent to avoid showing the MessageBox when restarting
        self.restarting = False

        # Set geometry to ratio of screen-geometry
        # (before adding func-buttons to allow adjustment to size)
        set_ratio_geometry(0.9, self)

        # Call window-methods
        self.init_menu()
        self.init_toolbar()
        self.init_docks()
        self.init_node_viewer()
        self.init_edu()

        center(self)
        self.show()

        # ToDo: Use statusbar more
        self.statusBar().showMessage("Initialization complete")

        self.first_init = False

    def update_project_ui(self):
        # Redraw function-buttons and parameter-widgets
        self.redraw_func_and_param()
        # Update Subject-Lists
        self.file_dock.update_dock()
        # Update Project-Box
        self.update_project_box()
        # Update Statusbar
        self.statusBar().showMessage(
            f"Home-Path: {self.ct.home_path}, Project: {self.pr.name}"
        )

    def change_home_path(self):
        # First save the former projects-data
        WorkerDialog(self, self.ct.save, blocking=True)

        new_home_path = compat.getexistingdirectory(
            self, "Change your Home-Path (top-level folder of Pipeline-Data)"
        )
        if new_home_path != "":
            try:
                new_controller = Controller(new_home_path)
            except RuntimeError as err:
                QMessageBox.critical(self, "Error with selected Home-Path", str(err))
            else:
                if new_controller.pr is None:
                    new_project = get_user_input(
                        "There is no project in this Home-Path,"
                        " please enter a name for a new project:",
                        "string",
                        force=True,
                    )
                    self.pr = new_controller.change_project(new_project)

                self.ct = new_controller
                welcome_window = _widgets["welcome_window"]
                if welcome_window is not None:
                    welcome_window.ct = new_controller
                self.statusBar().showMessage(
                    f"Home-Path: {self.ct.home_path}, Project: {self.pr.name}"
                )
                self.update_project_ui()

    def add_project(self):
        # First save the former projects-data
        WorkerDialog(self, self.pr.save, blocking=True)

        new_project = get_user_input("Enter a name for a new project", "string")
        if new_project is not None:
            self.pr = self.ct.change_project(new_project)
            self.update_project_ui()

    def remove_project(self):
        # First save the former projects-data
        WorkerDialog(self, self.pr.save, blocking=True)

        RemoveProjectsDlg(self, self.ct)

    def project_changed(self, idx):
        # First save the former projects-data
        WorkerDialog(self, self.pr.save, blocking=True)

        # Get selected Project
        project = self.project_box.itemText(idx)

        # Change project
        self.pr = self.ct.change_project(project)

        self.update_project_ui()

    def pr_rename(self):
        self.ct.rename_project()
        self.update_project_box()

    def pr_clean_fp(self):
        WorkerDialog(
            self,
            self.pr.clean_file_parameters,
            show_buttons=True,
            show_console=True,
            close_directly=False,
            title="Cleaning File-Parameters",
        )

    def pr_clean_pf(self):
        WorkerDialog(
            self,
            self.pr.clean_plot_files,
            show_buttons=True,
            show_console=True,
            close_directly=False,
            title="Cleaning Plot-Files",
        )

    def pr_copy_parameters(self):
        CopyParamsDialog(self)

    def update_project_box(self):
        self.project_box.clear()
        self.project_box.addItems(self.ct.projects)
        if self.pr is not None:
            self.project_box.setCurrentText(self.pr.name)

    def init_edu(self):
        if (
            Settings().get("education")
            and self.ct.edu_program
            and len(self.ct.edu_program["tour_list"]) > 0
        ):
            self.edu_tour = EducationTour(self, self.ct.edu_program)

    def init_menu(self):
        # & in front of text-string creates automatically a shortcut
        # with Alt + <letter after &>
        # Input
        import_menu = self.menuBar().addMenu("&Import")

        aaddfiles = QAction("Add MEEG", parent=self)
        aaddfiles.setShortcut("Ctrl+M")
        aaddfiles.setStatusTip("Add your MEG-Files here")
        aaddfiles.triggered.connect(partial(AddFilesDialog, self))
        import_menu.addAction(aaddfiles)

        import_menu.addAction("Add Sample-Dataset", self.add_sample_dataset)
        import_menu.addAction("Add Test-Dataset", self.add_test_dataset)
        import_menu.addAction("Reload raw", partial(ReloadRaw, self))

        import_menu.addSeparator()

        aaddmri = QAction("Add Freesurfer-MRI", self)
        aaddmri.setShortcut("Ctrl+F")
        aaddmri.setStatusTip("Add your Freesurfer-Segmentations here")
        aaddmri.triggered.connect(partial(AddMRIDialog, self))
        import_menu.addAction(aaddmri)

        import_menu.addAction("Add fsaverage", self.add_fsaverage)

        import_menu.addSeparator()

        import_menu.addAction("Show Info", partial(RawInfo, self))
        import_menu.addAction("File-Management", partial(FileManagment, self))

        export_menu = self.menuBar().addMenu("&Export")
        export_menu.addAction("Export MEEG", partial(ExportDialog, self))

        prep_menu = self.menuBar().addMenu("&Preparation")
        prep_menu.addAction("Subject-Wizard", partial(SubjectWizard, self))

        prep_menu.addSeparator()

        prep_menu.addAction(
            "Assign MEEG --> Freesurfer-MRI", partial(FileDictDialog, self, "mri")
        )
        prep_menu.addAction(
            "Assign MEEG --> Empty-Room", partial(FileDictDialog, self, "erm")
        )
        prep_menu.addAction(
            "Assign Bad-Channels --> MEEG", partial(SubBadsDialog, self)
        )
        prep_menu.addAction("Assign Event-IDs --> MEEG", partial(EventIDGui, self))
        prep_menu.addAction("Select ICA-Components", partial(ICASelect, self))

        prep_menu.addSeparator()

        prep_menu.addAction("MRI-Coregistration", mne.gui.coregistration)
        prep_menu.addAction("Copy Transformation", partial(CopyTrans, self))

        prep_menu.addSeparator()

        # Project
        project_menu = self.menuBar().addMenu("&Project")
        project_menu.addAction("&Rename Project", self.pr_rename)
        project_menu.addAction("&Clean File-Parameters", self.pr_clean_fp)
        project_menu.addAction("&Clean Plot-Files", self.pr_clean_pf)
        project_menu.addAction(
            "&Copy Parameters between Projects", self.pr_copy_parameters
        )

        # Custom-Functions
        func_menu = self.menuBar().addMenu("&Functions")
        func_menu.addAction("&Import Custom", partial(CustomFunctionImport, self))

        func_menu.addAction(
            "&Choose Custom-Modules", partial(ChooseCustomModules, self)
        )

        func_menu.addAction("&Reload Modules", self.ct.reload_modules)
        func_menu.addSeparator()
        func_menu.addAction("Additional Keyword-Arguments", partial(AddKwargs, self))

        # Education
        education_menu = self.menuBar().addMenu("&Education")
        if self.ct.edu_program is None:
            education_menu.addAction(
                "&Education-Editor", partial(EducationEditor, self)
            )
        else:
            education_menu.addAction("&Start Education-Tour", self.init_edu)

        # Tools
        tool_menu = self.menuBar().addMenu("&Tools")
        tool_menu.addAction("&Data-Terminal", partial(DataTerminal, self))
        tool_menu.addAction("&Plot-Viewer", partial(PlotViewSelection, self))

        # View
        self.view_menu = self.menuBar().addMenu("&View")
        if not ismac:
            self.view_menu.addAction("&Full-Screen", self.full_screen).setCheckable(
                True
            )

        # Settings
        settings_menu = self.menuBar().addMenu("&Settings")

        settings_menu.addAction("&Open Settings", partial(SettingsDlg, self, self.ct))
        settings_menu.addAction("&Customize Theme", partial(ColorTester, self))
        settings_menu.addAction("&Change Home-Path", self.change_home_path)
        settings_menu.addSeparator()
        # ToDo: Needs to be thoroughly tested on all OS
        # settings_menu.addAction('&Update Pipeline (stable)',
        #                         partial(self.update_pipeline, 'stable'))
        # settings_menu.addAction('&Update Pipeline (dev)',
        #                         partial(self.update_pipeline, 'dev'))
        # settings_menu.addAction('&Update MNE-Python', self.update_mne)
        settings_menu.addAction("&Restart", self.restart)

        # About
        about_menu = self.menuBar().addMenu("About")
        # about_menu.addAction('Update Pipeline', self.update_pipeline)
        # about_menu.addAction('Update MNE-Python', self.update_mne)
        about_menu.addAction("Quick-Guide", partial(QuickGuide, self))
        about_menu.addAction("MNE System-Info", self.show_sys_info)
        about_menu.addAction("About", partial(AboutDialog, self))
        about_menu.addAction("About QT", QApplication.instance().aboutQt)

    def init_toolbar(self):
        self.toolbar = self.addToolBar("Tools")
        # Add Project-UI
        proj_box_label = QLabel("<b>Project: </b>")
        self.toolbar.addWidget(proj_box_label)

        self.project_box = QComboBox()
        self.project_box.setSizeAdjustPolicy(CMBX_ADJUST_CONTENTS)
        self.project_box.activated.connect(self.project_changed)
        self.update_project_box()
        self.toolbar.addWidget(self.project_box)

        add_action = QAction(parent=self, icon=get_std_icon("SP_FileDialogNewFolder"))
        add_action.triggered.connect(self.add_project)
        self.toolbar.addAction(add_action)

        remove_action = QAction(
            parent=self, icon=get_std_icon("SP_DialogDiscardButton")
        )
        remove_action.triggered.connect(self.remove_project)
        self.toolbar.addAction(remove_action)
        self.toolbar.addSeparator()

        self.toolbar.addWidget(
            IntGui(
                data=Settings(),
                name="n_jobs",
                min_val=-1,
                special_value_text="Auto",
                description="Set to the amount of (virtual) cores "
                "of your machine you want "
                "to use for multiprocessing.",
                default=-1,
                groupbox_layout=False,
            )
        )
        # self.toolbar.addWidget(
        #     IntGui(data=QS(), name='n_parallel', min_val=1,
        #            description='Set to the amount of threads you want '
        #                        'to run simultaneously in the pipeline',
        #            default=1, groupbox_layout=False))
        # self.toolbar.addWidget(
        #     BoolGui(data=QS(), name='use_qthread', alias='Use QThreads',
        #             description='Check to use QThreads for running '
        #                         'the pipeline.\n'
        #                         'This is faster than the default'
        #                         ' with separate processes, '
        #                         'but has a few limitations',
        #             default=0, return_integer=True))
        # self.toolbar.addWidget(BoolGui(data=self.ct.settings, name='overwrite',
        #                                alias='Overwrite',
        #                                description='Check to overwrite files'
        #                                            ' even if their parameters '
        #                                            'where unchanged.',
        #                                groupbox_layout=False))
        self.toolbar.addWidget(
            BoolGui(
                data=self.ct.settings,
                name="show_plots",
                alias="Show Plots",
                description="Do you want to show"
                " plots?\n"
                "(or just save them without"
                " showing, then just check"
                ' "Save Plots").',
                groupbox_layout=False,
            )
        )
        self.toolbar.addWidget(
            BoolGui(
                data=self.ct.settings,
                name="save_plots",
                alias="Save Plots",
                description="Do you want to save the plots made to a file?",
                groupbox_layout=False,
            )
        )
        self.toolbar.addWidget(
            BoolGui(
                data=self.ct.settings,
                name="shutdown",
                alias="Shutdown",
                description="Do you want to shut your "
                "system down after "
                " execution of all "
                "subjects?",
                groupbox_layout=False,
            )
        )
        close_all_bt = QPushButton("Close All Plots")
        close_all_bt.pressed.connect(close_all)
        self.toolbar.addWidget(close_all_bt)

    def init_main_widget(self):
        self.setCentralWidget(QWidget(self))
        self.general_layout = QGridLayout()
        self.centralWidget().setLayout(self.general_layout)

        self.tab_func_widget = QTabWidget()
        self.general_layout.addWidget(self.tab_func_widget, 0, 0, 1, 3)

        # Show already here to get the width of tab_func_widget to fit
        # the function-groups inside
        self.show()
        self.general_layout.invalidate()

        # Add Function-Buttons
        self.add_func_bts()

        # Add Main-Buttons
        clear_bt = QPushButton("Clear")
        start_bt = QPushButton("Start")
        stop_bt = QPushButton("Quit")

        clear_bt.setFont(QFont(Settings().get("app_font"), 18))
        start_bt.setFont(QFont(Settings().get("app_font"), 18))
        stop_bt.setFont(QFont(Settings().get("app_font"), 18))

        clear_bt.clicked.connect(self.clear)
        start_bt.clicked.connect(self.start)
        stop_bt.clicked.connect(self.close)

        self.general_layout.addWidget(clear_bt, 1, 0)
        self.general_layout.addWidget(start_bt, 1, 1)
        self.general_layout.addWidget(stop_bt, 1, 2)

    def init_node_viewer(self):
        # Initialize Node-Viewer
        self.node_viewer = NodeViewer(self.ct, self)
        self.setCentralWidget(self.node_viewer)

    def add_func_bts(self):
        # Drop custom-modules, which aren't selected
        cleaned_pd_funcs = self.ct.pd_funcs.loc[
            self.ct.pd_funcs["module"].isin(self.ct.get_setting("selected_modules"))
        ].copy()
        # Horizontal Border for Function-Groups
        max_h_size = self.tab_func_widget.geometry().width()

        # Assert, that cleaned_pd_funcs is not empty
        # (possible, when deselecting all modules)
        if len(cleaned_pd_funcs) != 0:
            tabs_grouped = cleaned_pd_funcs.groupby("tab")
            # Add tabs
            for tab_name, group in tabs_grouped:
                group_grouped = group.groupby("group", sort=False)
                tab = QScrollArea()
                child_w = QWidget()
                tab_v_layout = QVBoxLayout()
                tab_h_layout = QHBoxLayout()
                h_size = 0
                # Add groupbox for each group
                for function_group, _ in group_grouped:
                    group_box = QGroupBox(function_group, self)
                    group_box.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
                    setattr(self, f"{function_group}_gbox", group_box)
                    group_box.setCheckable(True)
                    group_box.toggled.connect(self.func_group_toggled)
                    group_box_layout = QVBoxLayout()
                    # Add button for each function
                    for function in group_grouped.groups[function_group]:
                        if pd.notna(cleaned_pd_funcs.loc[function, "alias"]):
                            alias_name = cleaned_pd_funcs.loc[function, "alias"]
                        else:
                            alias_name = function
                        pb = QPushButton(alias_name)
                        pb.setAutoFillBackground(True)
                        pb.setCheckable(True)
                        self.bt_dict[function] = pb
                        if function in self.pr.sel_functions:
                            pb.setChecked(True)
                        pb.clicked.connect(partial(self.func_selected, function))
                        group_box_layout.addWidget(pb)

                    group_box.setLayout(group_box_layout)
                    h_size += group_box.sizeHint().width()
                    if h_size > max_h_size:
                        tab_v_layout.addLayout(tab_h_layout)
                        h_size = group_box.sizeHint().width()
                        tab_h_layout = QHBoxLayout()
                    tab_h_layout.addWidget(group_box, alignment=ALIGN_LEFT | ALIGN_TOP)

                if tab_h_layout.count() > 0:
                    tab_v_layout.addLayout(tab_h_layout)

                child_w.setLayout(tab_v_layout)
                tab.setWidget(child_w)
                self.tab_func_widget.addTab(tab, tab_name)
        set_app_theme()

        # Add experimental Node-Tab
        self.node_viewer = NodeViewer(self.ct, self)
        self.tab_func_widget.addTab(self.node_viewer, "Node-Graph")
        self.tab_func_widget.setCurrentWidget(self.node_viewer)

        demo_dict = {
            "Filter Raw": {
                "parameters": {
                    "low_cutoff": {
                        "alias": "Low-Cutoff",
                        "gui": "FloatGui",
                        "default": 0.1,
                    },
                    "high_cutoff": {
                        "alias": "High-Cutoff",
                        "gui": "FloatGui",
                        "default": 0.2,
                    },
                },
                "ports": [
                    {"name": "Raw", "port_type": "in"},
                    {"name": "Raw", "port_type": "out", "multi_connection": True},
                ],
            },
            "Get Events": {
                "parameters": {
                    "event_id": {"alias": "Event-ID", "gui": "IntGui", "default": 1}
                },
                "ports": [
                    {"name": "Raw", "port_type": "in"},
                    {"name": "Events", "port_type": "out", "multi_connection": True},
                ],
            },
            "Epoch Data": {
                "parameters": {
                    "epochs_tmin": {
                        "alias": "tmin",
                        "gui": "FloatGui",
                        "default": -0.2,
                    },
                    "epochs_tmax": {"alias": "tmax", "gui": "FloatGui", "default": 0.5},
                    "apply_baseline": {
                        "alias": "Baseline",
                        "gui": "BoolGui",
                        "default": True,
                    },
                },
                "ports": [
                    {"name": "Raw", "port_type": "in"},
                    {"name": "Events", "port_type": "in"},
                    {"name": "Epochs", "port_type": "out", "multi_connection": True},
                ],
            },
            "Average Epochs": {
                "parameters": {
                    "event_id": {"alias": "Event-ID", "gui": "IntGui", "default": 1}
                },
                "ports": [
                    {"name": "Epochs", "port_type": "in"},
                    {"name": "Evokeds", "port_type": "out", "multi_connection": True},
                ],
            },
            "Make Forward Model": {
                "parameters": {
                    "fwd_subject": {
                        "alias": "Forward Subject",
                        "gui": "StringGui",
                        "default": "fsaverage",
                    }
                },
                "ports": [
                    {"name": "MRI", "port_type": "in"},
                    {"name": "Fwd", "port_type": "out", "multi_connection": True},
                ],
            },
            "Make Inverse Operator": {
                "parameters": {
                    "inv_subject": {
                        "alias": "Inverse Subject",
                        "gui": "StringGui",
                        "default": "fsaverage",
                    }
                },
                "ports": [
                    {"name": "Evokeds", "port_type": "in"},
                    {"name": "Fwd", "port_type": "in"},
                    {"name": "Inv", "port_type": "out", "multi_connection": True},
                ],
            },
            "Plot Source Estimates": {
                "parameters": {
                    "subject": {
                        "alias": "Subject",
                        "gui": "StringGui",
                        "default": "fsaverage",
                    }
                },
                "ports": [
                    {"name": "Inv", "port_type": "in"},
                    {"name": "Plot", "port_type": "out", "multi_connection": True},
                ],
            },
        }

        # Add some demo nodes
        meeg_node = self.node_viewer.create_node("MEEGInputNode")
        mri_node = self.node_viewer.create_node("MRIInputNode")
        ass_node = self.node_viewer.create_node(
            node_class="AssignmentNode",
            name="Assignment",
            ports=[
                {"name": "Evokeds", "port_type": "in"},
                {"name": "Fwd", "port_type": "in"},
                {"name": "Evokeds", "port_type": "out"},
                {"name": "Fwd", "port_type": "out"},
            ],
        )
        fn = {}
        for func_name, func_kwargs in demo_dict.items():
            fnode = self.node_viewer.create_node("FunctionNode", **func_kwargs)
            fn[func_name] = fnode

        # Wire up the nodes
        meeg_node.output(port_idx=0).connect_to(fn["Filter Raw"].input(port_idx=0))
        meeg_node.output(port_idx=0).connect_to(fn["Get Events"].input(port_idx=0))
        fn["Epoch Data"].input(port_name="Raw").connect_to(
            fn["Filter Raw"].output(port_idx=0)
        )
        fn["Epoch Data"].input(port_name="Events").connect_to(
            fn["Get Events"].output(port_idx=0)
        )
        fn["Epoch Data"].output(port_name="Epochs").connect_to(
            fn["Average Epochs"].input(port_name="Epochs")
        )

        mri_node.output(port_idx=0).connect_to(
            fn["Make Forward Model"].input(port_name="MRI")
        )

        ass_node.input(port_idx=0).connect_to(
            fn["Average Epochs"].output(port_name="Evokeds")
        )
        ass_node.input(port_idx=1).connect_to(
            fn["Make Forward Model"].output(port_name="Fwd")
        )
        ass_node.output(port_idx=0).connect_to(
            fn["Make Inverse Operator"].input(port_name="Evokeds")
        )
        ass_node.output(port_idx=1).connect_to(
            fn["Make Inverse Operator"].input(port_name="Fwd")
        )

        fn["Plot Source Estimates"].input(port_name="Inv").connect_to(
            fn["Make Inverse Operator"].output(port_name="Inv")
        )

        self.node_viewer.auto_layout_nodes()
        self.node_viewer.clear_selection()
        self.node_viewer.fit_to_selection()

    def redraw_func_and_param(self):
        self.parameters_dock.redraw_param_widgets()

    def _update_selected_functions(self, function, checked):
        if checked:
            if function not in self.pr.sel_functions:
                self.pr.sel_functions.append(function)
        elif function in self.pr.sel_functions:
            self.pr.sel_functions.remove(function)

    def func_selected(self, function):
        self._update_selected_functions(function, self.bt_dict[function].isChecked())

    def func_group_toggled(self):
        for function in self.bt_dict:
            self._update_selected_functions(
                function,
                self.bt_dict[function].isChecked()
                and self.bt_dict[function].isEnabled(),
            )

    def update_selected_funcs(self):
        for function in self.bt_dict:
            self.bt_dict[function].setChecked(False)
            if function in self.pr.sel_functions:
                self.bt_dict[function].setChecked(True)

    def init_docks(self):
        if self.ct.edu_program:
            dock_kwargs = self.ct.edu_program["dock_kwargs"]
        else:
            dock_kwargs = {}
        self.file_dock = FileDock(self, **dock_kwargs)
        self.addDockWidget(LEFT_DOCK, self.file_dock)
        self.view_menu.addAction(self.file_dock.toggleViewAction())

        self.parameters_dock = ParametersDock(self)
        self.addDockWidget(RIGHT_DOCK, self.parameters_dock)
        self.view_menu.addAction(self.parameters_dock.toggleViewAction())

    def add_sample_dataset(self):
        if "_sample_" in self.pr.all_meeg:
            QMessageBox.information(
                self,
                "_sample_ exists!",
                "The sample-dataset is already imported as _sample_!",
            )
        else:
            WorkerDialog(
                self,
                partial(self.pr.add_meeg, "_sample_"),
                show_console=True,
                title="Loading Sample...",
                blocking=True,
            )
            self.file_dock.update_dock()

    def add_test_dataset(self):
        if "_test_" in self.pr.all_meeg:
            QMessageBox.information(
                self,
                "_test_ exists!",
                "The test-dataset is already imported as _test_!",
            )
        else:
            WorkerDialog(
                self,
                partial(self.pr.add_meeg, "_test_"),
                show_console=True,
                title="Loading Sample...",
                blocking=True,
            )
            self.file_dock.update_dock()

    def add_fsaverage(self):
        if "fsaverage" in self.pr.all_fsmri:
            QMessageBox.information(
                self, "fsaverage exists!", "fsaverage is already imported!"
            )
        else:
            WorkerDialog(
                self,
                partial(self.pr.add_fsmri, "fsaverage"),
                show_console=True,
                title="Loading fsaverage...",
                blocking=True,
            )
            self.file_dock.update_dock()

    def full_screen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def clear(self):
        for x in self.bt_dict:
            self.bt_dict[x].setChecked(False)
        self.pr.sel_functions.clear()

    def start(self):
        if self.pipeline_running:
            QMessageBox.warning(
                self, "Already running!", "The Pipeline is already running!"
            )
        else:
            WorkerDialog(
                self,
                self.ct.save,
                show_buttons=False,
                show_console=False,
                blocking=True,
            )
            self.run_dialog = RunDialog(self)

    def restart(self):
        self.restarting = True
        self.close()
        restart_program()

    def update_pipeline(self, version):
        if version == "stable":
            command = "pip install --upgrade mne_nodes"
        else:
            command = "pip install https://github.com/marsipu/mne-nodes/zipball/main"
        if iswin and not _run_from_script():
            QMessageBox.information(
                self,
                "Manual install required!",
                f"To update you need to exit the program "
                f'and type "{command}" into the terminal!',
            )
        else:
            QProcessDialog(
                self,
                command,
                show_buttons=True,
                show_console=True,
                close_directly=True,
                title="Updating Pipeline...",
                blocking=True,
            )

            answer = QMessageBox.question(
                self,
                "Do you want to restart?",
                "Please restart the Pipeline-Program "
                "to apply the changes from the Update!",
            )

            if answer == MB_YES:
                self.restart()

    def update_mne(self):
        command = "pip install --upgrade mne"
        QProcessDialog(
            self,
            command,
            show_buttons=True,
            show_console=True,
            close_directly=True,
            title="Updating MNE-Python...",
            blocking=True,
        )

        answer = QMessageBox.question(
            self,
            "Do you want to restart?",
            "Please restart the Pipeline-Program to apply the changes from the Update!",
        )

        if answer == MB_YES:
            self.restart()

    def show_sys_info(self):
        SysInfoMsg(self)
        mne.sys_info()

    def closeEvent(self, event):
        welcome_window = _widgets["welcome_window"]
        if self.restarting or welcome_window is None:
            answer = QMessageBox.No
        else:
            answer = QMessageBox.question(
                self,
                "Closing MNE-Pipeline",
                "Do you want to return to the Welcome-Window?",
                buttons=MB_YES | MB_NO | MB_CANCEL,
                defaultButton=MB_YES,
            )
        if answer not in [MB_YES, MB_NO]:
            event.ignore()
        else:
            if self.edu_tour:
                self.edu_tour.close()
            event.accept()
            _widgets["main_window"] = None

            if welcome_window is not None:
                if answer == MB_YES:
                    welcome_window.update_widgets()
                    welcome_window.show()

                elif answer == MB_NO:
                    welcome_window.close()


class CopyParamsDialog(SimpleDialog):
    def __init__(self, main_win):
        self.main_win = main_win
        self.ct = main_win.ct
        widget = QWidget()
        layout = QGridLayout()
        layout.addWidget(QLabel("From:"), 0, 0)
        self.from_cmbx = QComboBox()
        self.from_cmbx.addItems(self.ct.projects)
        self.from_cmbx.currentTextChanged.connect(self.from_selected)
        layout.addWidget(self.from_cmbx, 1, 0)
        layout.addWidget(QLabel("Parameter-Preset:"), 2, 0)
        self.from_pp_cmbx = QComboBox()
        self.from_pp_cmbx.currentTextChanged.connect(self.from_pp_selected)
        layout.addWidget(self.from_pp_cmbx, 3, 0)

        layout.addWidget(QLabel("To:"), 0, 1)
        self.to_cmbx = QComboBox()
        self.to_cmbx.currentTextChanged.connect(self.to_selected)
        layout.addWidget(self.to_cmbx, 1, 1)
        layout.addWidget(QLabel("Parameter-Preset:"), 2, 1)
        self.to_pp_cmbx = QComboBox()
        self.to_pp_cmbx.setEditable(True)
        layout.addWidget(self.to_pp_cmbx, 3, 1)

        layout.addWidget(QLabel("Parameter:"), 4, 0, 1, 2)
        self.param_cmbx = QComboBox()
        layout.addWidget(self.param_cmbx, 5, 0, 1, 2)

        copy_bt = QPushButton("Copy")
        copy_bt.clicked.connect(self.copy_parameters)
        layout.addWidget(copy_bt, 6, 0)
        close_bt = QPushButton("Close")
        close_bt.clicked.connect(self.close)
        layout.addWidget(close_bt, 6, 1)

        widget.setLayout(layout)
        super().__init__(
            widget,
            parent=main_win,
            title="Copy Parameters between Projects",
            window_title="Copy Parameters",
            show_close_bt=False,
        )

        # Initialize with first from-entry
        self.from_selected(self.from_cmbx.currentText())

    def _get_p_presets(self, pr_name):
        if self.ct.pr.name == pr_name:
            project = self.ct.pr
        else:
            project = Project(self.ct, pr_name)

        return list(project.parameters.keys())

    def from_pp_selected(self, from_pp_name):
        if from_pp_name:
            self.param_cmbx.clear()
            params = list(
                Project(self.ct, self.from_cmbx.currentText())
                .parameters[from_pp_name]
                .keys()
            )
            params.insert(0, "<all>")
            self.param_cmbx.addItems(params)

    def from_selected(self, from_name):
        if from_name:
            self.to_cmbx.clear()
            self.to_cmbx.addItems([p for p in self.ct.projects if p != from_name])

            self.from_pp_cmbx.clear()
            self.from_pp_cmbx.addItems(self._get_p_presets(from_name))

            self.from_pp_selected(self.from_pp_cmbx.currentText())

    def to_selected(self, to_name):
        if to_name:
            self.to_pp_cmbx.clear()
            self.to_pp_cmbx.addItems(self._get_p_presets(to_name))

    def copy_parameters(self):
        from_name = self.from_cmbx.currentText()
        from_pp = self.from_pp_cmbx.currentText()
        to_name = self.to_cmbx.currentText()
        to_pp = self.to_pp_cmbx.currentText()
        param = self.param_cmbx.currentText()
        if param == "<all>":
            param = None
        if from_name and to_name:
            self.ct.copy_parameters_between_projects(
                from_name, from_pp, to_name, to_pp, param
            )
        if to_name == self.ct.pr.name:
            self.main_win.parameters_dock.redraw_param_widgets()
        QMessageBox().information(
            self,
            "Finished",
            f"Copied parameter '{param}' from {from_name} to {to_name}!",
        )


class RunDialog(QDialog):
    def __init__(self, main_win):
        super().__init__(main_win)
        self.mw = main_win

        self.init_controller()
        self.init_ui()

        set_ratio_geometry(0.6, self)
        self.show()

        self.start()

    def init_controller(self):
        self.rc = QRunController(run_dialog=self, controller=self.mw.ct)

    def init_ui(self):
        layout = QVBoxLayout()

        view_layout = QGridLayout()
        view_layout.addWidget(QLabel("Objects: "), 0, 0)
        self.object_view = QListView()
        self.object_model = RunModel(self.rc.all_objects, mode="object")
        self.object_view.setModel(self.object_model)
        self.object_view.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        view_layout.addWidget(self.object_view, 1, 0)

        view_layout.addWidget(QLabel("Functions: "), 0, 1)
        self.func_view = QListView()
        self.func_model = RunModel(self.rc.current_all_funcs, mode="func")
        self.func_view.setModel(self.func_model)
        self.func_view.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        view_layout.addWidget(self.func_view, 1, 1)

        view_layout.addWidget(QLabel("Errors: "), 0, 2)
        self.error_widget = SimpleList([])
        self.error_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        # Connect Signal from error_widget to function
        # to enable inspecting the errors
        self.error_widget.currentChanged.connect(self.show_error)
        view_layout.addWidget(self.error_widget, 1, 2)

        layout.addLayout(view_layout)

        self.console_widget = MainConsoleWidget()
        layout.addWidget(self.console_widget)

        self.pgbar = QProgressBar()
        self.pgbar.setValue(0)
        self.pgbar.setMaximum(len(self.rc.all_steps))
        layout.addWidget(self.pgbar)

        bt_layout = QHBoxLayout()

        self.continue_bt = QPushButton("Continue")
        self.continue_bt.setFont(QFont("AnyStyle", 14))
        self.continue_bt.setIcon(get_std_icon("SP_MediaPlay"))
        self.continue_bt.clicked.connect(self.start)
        bt_layout.addWidget(self.continue_bt)

        self.pause_bt = QPushButton("Pause")
        self.pause_bt.setFont(QFont("AnyStyle", 14))
        self.pause_bt.setIcon(get_std_icon("SP_MediaPause"))
        self.pause_bt.clicked.connect(self.pause_funcs)
        bt_layout.addWidget(self.pause_bt)

        self.restart_bt = QPushButton("Restart")
        self.restart_bt.setFont(QFont("AnyStyle", 14))
        self.restart_bt.setIcon(get_std_icon("SP_BrowserReload"))
        self.restart_bt.clicked.connect(self.restart)
        bt_layout.addWidget(self.restart_bt)

        self.reload_chbx = QCheckBox("Reload Modules")
        bt_layout.addWidget(self.reload_chbx)

        self.autoscroll_bt = QPushButton("Auto-Scroll")
        self.autoscroll_bt.setCheckable(True)
        self.autoscroll_bt.setChecked(True)
        self.autoscroll_bt.setIcon(get_std_icon("SP_DialogOkButton"))
        self.autoscroll_bt.clicked.connect(self.toggle_autoscroll)
        bt_layout.addWidget(self.autoscroll_bt)

        self.close_bt = QPushButton("Close")
        self.close_bt.setFont(QFont("AnyStyle", 14))
        self.close_bt.setIcon(get_std_icon("SP_MediaStop"))
        self.close_bt.clicked.connect(self.close)
        bt_layout.addWidget(self.close_bt)
        layout.addLayout(bt_layout)

        self.setLayout(layout)

    def start(self):
        # Set paused to false
        self.rc.paused = False
        # Enable/Disable Buttons
        self.continue_bt.setEnabled(False)
        self.pause_bt.setEnabled(True)
        self.restart_bt.setEnabled(False)
        self.close_bt.setEnabled(False)

        self.rc.start()

    def pause_funcs(self):
        self.rc.paused = True
        self.console_widget.write_html("<br><b>Finishing last function...</b><br>")

    def restart(self):
        # Reinitialize controller
        self.init_controller()

        # ToDo: MP
        # if self.reload_chbx and self.reload_chbx.isChecked():
        #     init_mp_pool()
        if self.reload_chbx.isChecked():
            self.mw.ct.reload_modules()

        # Clear Console-Widget
        self.console_widget.clear()

        # Redo References to display-widgets
        self.object_model._data = self.rc.all_objects
        self.object_model.layoutChanged.emit()
        self.func_model._data = self.rc.current_all_funcs
        self.func_model.layoutChanged.emit()
        self.error_widget.replace_data(list(self.rc.errors.keys()))

        # Reset Progress-Bar
        self.pgbar.setValue(0)

        # Restart
        self.start()

    def toggle_autoscroll(self, state):
        if state:
            self.console_widget.set_autoscroll(True)
        else:
            self.console_widget.set_autoscroll(False)

    def show_error(self, current, previous):
        self.console_widget.set_autoscroll(False)
        self.autoscroll_bt.setChecked(False)
        if current < previous:
            self.console_widget.find(
                f"Error-No. {self.rc.errors[current][1]} (above)",
                QTextDocument.FindBackward,
            )
        else:
            self.console_widget.find(f"Error-No. {self.rc.errors[current][1]} (above)")

    def closeEvent(self, event):
        self.mw.pipeline_running = False
        event.accept()


class CustomFunctionImport(QDialog):
    def __init__(self, main_win):
        super().__init__(main_win)
        self.mw = main_win
        self.ct = main_win.ct
        self.file_path = None
        self.pkg_name = None
        self.current_function = None
        self.current_parameter = None
        self.oblig_func = ["target", "tab", "group", "matplotlib", "mayavi"]
        self.oblig_params = ["default", "gui_type"]

        self.exst_functions = list(self.ct.pd_funcs.index)
        self.exst_parameters = ["mw", "pr", "meeg", "fsmri", "group"]
        self.exst_parameters += list(self.ct.settings.keys())
        self.exst_parameters += list(Settings().keys())
        self.exst_parameters += list(self.ct.pr.parameters[self.ct.pr.p_preset].keys())
        self.param_exst_dict = {}

        self.code_editor = None
        self.code_dict = {}

        # Get available parameter-guis
        self.available_param_guis = [
            pg for pg in dir(parameter_widgets) if "Gui" in pg and pg != "QtGui"
        ]

        self.add_pd_funcs = pd.DataFrame(
            columns=[
                "alias",
                "target",
                "tab",
                "group",
                "matplotlib",
                "mayavi",
                "dependencies",
                "module",
                "func_args",
                "ready",
            ]
        )
        self.add_pd_params = pd.DataFrame(
            columns=[
                "alias",
                "group",
                "default",
                "unit",
                "description",
                "gui_type",
                "gui_args",
                "functions",
                "ready",
            ]
        )

        self.yes_icon = get_std_icon("SP_DialogApplyButton")
        self.no_icon = get_std_icon("SP_DialogCancelButton")

        self.setWindowTitle("Custom-Functions-Setup")

        self.init_ui()
        self.open()

    def init_ui(self):
        layout = QVBoxLayout()

        # Import Button and Combobox
        add_bt_layout = QHBoxLayout()
        addfn_bt = QPushButton("Load Function/s")
        addfn_bt.setFont(QFont(Settings().get("app_font"), 12))
        addfn_bt.clicked.connect(self.get_functions)
        add_bt_layout.addWidget(addfn_bt)
        editfn_bt = QPushButton("Edit Function/s")
        editfn_bt.setFont(QFont(Settings().get("app_font"), 12))
        editfn_bt.clicked.connect(self.edit_functions)
        add_bt_layout.addWidget(editfn_bt)
        layout.addLayout(add_bt_layout)

        # Function-ComboBox
        func_cmbx_layout = QHBoxLayout()
        self.func_cmbx = QComboBox()
        self.func_cmbx.currentTextChanged.connect(self.func_item_selected)
        func_cmbx_layout.addWidget(self.func_cmbx)

        self.func_chkl = QLabel()
        self.func_chkl.setPixmap(self.no_icon.pixmap(16, 16))
        self.func_chkl.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
        func_cmbx_layout.addWidget(self.func_chkl)
        layout.addLayout(func_cmbx_layout)

        # Hint for obligatory items
        # There may be a better way to center the labels
        # instead of with the space-labels
        obl_hint_layout = QHBoxLayout()
        space_label1 = QLabel("")
        obl_hint_layout.addWidget(space_label1)
        obl_hint_label1 = QLabel()
        obl_hint_label1.setPixmap(self.no_icon.pixmap(16, 16))
        obl_hint_label1.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
        obl_hint_layout.addWidget(obl_hint_label1)
        obl_hint_label2 = QLabel()
        obl_hint_label2.setPixmap(get_std_icon("SP_ArrowForward").pixmap(16, 16))
        obl_hint_label2.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
        obl_hint_layout.addWidget(obl_hint_label2)
        obl_hint_label3 = QLabel()
        obl_hint_label3.setPixmap(self.yes_icon.pixmap(16, 16))
        obl_hint_label3.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
        obl_hint_layout.addWidget(obl_hint_label3)
        obl_hint_label4 = QLabel("(= The items marked are obligatory)")
        obl_hint_label4.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
        obl_hint_layout.addWidget(obl_hint_label4)
        space_label2 = QLabel("")
        obl_hint_layout.addWidget(space_label2)
        layout.addLayout(obl_hint_layout)

        setup_layout = QHBoxLayout()
        # The Function-Setup-Groupbox
        func_setup_gbox = QGroupBox("Function-Setup")
        func_setup_gbox.setAlignment(ALIGN_CENTER)
        func_setup_formlayout = QFormLayout()

        self.falias_le = QLineEdit()
        self.falias_le.setToolTip(
            "Set a name if you want something other than the functions-name"
        )
        self.falias_le.textEdited.connect(self.falias_changed)
        func_setup_formlayout.addRow("Alias", self.falias_le)

        target_layout = QHBoxLayout()
        self.target_cmbx = QComboBox()
        self.target_cmbx.setToolTip(
            "Set the target on which the function shall operate"
        )
        self.target_cmbx.setEditable(False)
        self.target_cmbx.activated.connect(self.target_cmbx_changed)
        target_layout.addWidget(self.target_cmbx)
        self.target_chkl = QLabel()
        target_layout.addWidget(self.target_chkl)
        func_setup_formlayout.addRow("Target", target_layout)

        tab_layout = QHBoxLayout()
        self.tab_cmbx = QComboBox()
        self.tab_cmbx.setToolTip("Choose the Tab for the function (Compute/Plot/...)")
        self.tab_cmbx.setEditable(True)
        self.tab_cmbx.activated.connect(self.tab_cmbx_changed)
        self.tab_cmbx.editTextChanged.connect(self.tab_cmbx_edited)
        tab_layout.addWidget(self.tab_cmbx)
        self.tab_chkl = QLabel()
        tab_layout.addWidget(self.tab_chkl)
        func_setup_formlayout.addRow("Tab", tab_layout)

        group_layout = QHBoxLayout()
        self.group_cmbx = QComboBox()
        self.group_cmbx.setToolTip(
            "Choose the function-group for the function or create a new one"
        )
        self.group_cmbx.setEditable(True)
        self.group_cmbx.activated.connect(self.group_cmbx_changed)
        self.group_cmbx.editTextChanged.connect(self.group_cmbx_edited)
        group_layout.addWidget(self.group_cmbx)
        self.group_chkl = QLabel()
        group_layout.addWidget(self.group_chkl)
        func_setup_formlayout.addRow("Group", group_layout)

        mtpl_layout = QHBoxLayout()
        self.mtpl_bts = QButtonGroup(self)
        self.mtpl_yesbt = QPushButton("Yes")
        self.mtpl_yesbt.setCheckable(True)
        self.mtpl_nobt = QPushButton("No")
        self.mtpl_nobt.setCheckable(True)
        self.mtpl_void = QPushButton("")
        self.mtpl_void.setCheckable(True)
        self.mtpl_bts.addButton(self.mtpl_yesbt)
        self.mtpl_bts.addButton(self.mtpl_nobt)
        self.mtpl_bts.addButton(self.mtpl_void)
        mtpl_layout.addWidget(self.mtpl_yesbt)
        mtpl_layout.addWidget(self.mtpl_nobt)
        self.mtpl_yesbt.setToolTip(
            "Choose, if the function contains an interactive Matplotlib-Plot"
        )
        self.mtpl_nobt.setToolTip(
            "Choose, if the function contains no interactive Matplotlib-Plot"
        )
        self.mtpl_bts.buttonToggled.connect(self.mtpl_changed)
        self.mtpl_chkl = QLabel()
        mtpl_layout.addWidget(self.mtpl_chkl)
        func_setup_formlayout.addRow("Matplotlib?", mtpl_layout)

        myv_layout = QHBoxLayout()
        self.myv_bts = QButtonGroup(self)
        self.myv_yesbt = QPushButton("Yes")
        self.myv_yesbt.setCheckable(True)
        self.myv_nobt = QPushButton("No")
        self.myv_nobt.setCheckable(True)
        self.myv_void = QPushButton("")
        self.myv_void.setCheckable(True)
        self.myv_bts.addButton(self.myv_yesbt)
        self.myv_bts.addButton(self.myv_nobt)
        self.myv_bts.addButton(self.myv_void)
        myv_layout.addWidget(self.myv_yesbt)
        myv_layout.addWidget(self.myv_nobt)
        self.myv_yesbt.setToolTip(
            "Choose, if the function contains a Pyvista/Mayavi-Plot"
        )
        self.myv_nobt.setToolTip(
            "Choose, if the function contains a Pyvista/Mayavi-Plot"
        )
        self.myv_bts.buttonToggled.connect(self.myv_changed)
        self.myv_chkl = QLabel()
        myv_layout.addWidget(self.myv_chkl)
        func_setup_formlayout.addRow("Pyvista/Mayavi?", myv_layout)

        self.dpd_bt = QPushButton("Set Dependencies")
        self.dpd_bt.setToolTip(
            "Set the functions that must be activated before or the "
            "files that must be present for this function to work"
        )
        self.dpd_bt.clicked.connect(partial(SelectDependencies, self))
        func_setup_formlayout.addRow("Dependencies", self.dpd_bt)

        func_setup_gbox.setLayout(func_setup_formlayout)
        setup_layout.addWidget(func_setup_gbox)

        # The Parameter-Setup-Group-Box
        self.param_setup_gbox = QGroupBox("Parameter-Setup")
        self.param_setup_gbox.setAlignment(ALIGN_HCENTER)
        param_setup_layout = QVBoxLayout()
        self.exstparam_l = QLabel()
        self.exstparam_l.setWordWrap(True)
        self.exstparam_l.hide()
        param_setup_layout.addWidget(self.exstparam_l)

        self.param_view = QListView()
        self.param_model = CustomFunctionModel(self.add_pd_params)
        self.param_view.setModel(self.param_model)
        self.param_view.selectionModel().currentChanged.connect(
            self.param_item_selected
        )
        param_setup_layout.addWidget(self.param_view)

        param_setup_formlayout = QFormLayout()
        self.palias_le = QLineEdit()
        self.palias_le.setToolTip(
            "Set a name if you want something other than the parameters-name"
        )
        self.palias_le.textEdited.connect(self.palias_changed)
        param_setup_formlayout.addRow("Alias", self.palias_le)

        default_layout = QHBoxLayout()
        self.default_le = QLineEdit()
        self.default_le.setToolTip(
            "Set the default for the parameter (it has to fit the gui-type!)"
        )
        self.default_le.textEdited.connect(self.pdefault_changed)
        default_layout.addWidget(self.default_le)
        self.default_chkl = QLabel()
        default_layout.addWidget(self.default_chkl)
        param_setup_formlayout.addRow("Default", default_layout)

        self.unit_le = QLineEdit()
        self.unit_le.setToolTip("Set the unit for the parameter (optional)")
        self.unit_le.textEdited.connect(self.punit_changed)
        param_setup_formlayout.addRow("Unit", self.unit_le)

        self.description_le = QLineEdit()
        self.description_le.setToolTip("Short description of the parameter (optional)")
        self.description_le.textEdited.connect(self.pdescription_changed)
        param_setup_formlayout.addRow("Description", self.description_le)

        guitype_layout = QHBoxLayout()
        self.guitype_cmbx = QComboBox()
        self.guitype_cmbx.setToolTip("Choose the GUI from the available GUIs")
        self.guitype_cmbx.activated.connect(self.guitype_cmbx_changed)
        guitype_layout.addWidget(self.guitype_cmbx)
        test_bt = QPushButton("Test")
        test_bt.clicked.connect(self.show_param_gui)
        guitype_layout.addWidget(test_bt)
        self.guitype_chkl = QLabel()
        guitype_layout.addWidget(self.guitype_chkl)
        param_setup_formlayout.addRow("GUI-Type", guitype_layout)

        self.guiargs_bt = QPushButton("Edit")
        self.guiargs_bt.clicked.connect(partial(EditGuiArgsDlg, self))
        self.guiargs_bt.setToolTip("Set Arguments for the GUI in a dict (optional)")
        param_setup_formlayout.addRow("Additional Options", self.guiargs_bt)

        param_setup_layout.addLayout(param_setup_formlayout)
        self.param_setup_gbox.setLayout(param_setup_layout)

        setup_layout.addWidget(self.param_setup_gbox)
        layout.addLayout(setup_layout)

        bt_layout = QHBoxLayout()

        save_bt = QPushButton("Save")
        save_bt.setFont(QFont(Settings().get("app_font"), 16))
        save_bt.clicked.connect(self.save_pkg)
        bt_layout.addWidget(save_bt)

        src_bt = QPushButton("Show Code")
        src_bt.setFont(QFont(Settings().get("app_font"), 16))
        src_bt.clicked.connect(self.show_code)
        bt_layout.addWidget(src_bt)

        close_bt = QPushButton("Quit")
        close_bt.setFont(QFont(Settings().get("app_font"), 16))
        close_bt.clicked.connect(self.close)
        bt_layout.addWidget(close_bt)

        layout.addLayout(bt_layout)

        self.setLayout(layout)

        self.populate_target_cmbx()
        self.populate_tab_cmbx()
        self.populate_group_cmbx()
        self.populate_guitype_cmbx()

    def update_func_cmbx(self):
        self.func_cmbx.clear()
        self.func_cmbx.insertItems(0, self.add_pd_funcs.index)
        try:
            current_index = list(self.add_pd_funcs.index).index(self.current_function)
        except ValueError:
            current_index = 0
        self.func_cmbx.setCurrentIndex(current_index)

    def clear_func_items(self):
        self.falias_le.clear()
        self.target_cmbx.setCurrentIndex(-1)
        self.target_chkl.setPixmap(self.no_icon.pixmap(QSize(16, 16)))
        self.tab_cmbx.setCurrentIndex(-1)
        self.tab_chkl.setPixmap(self.no_icon.pixmap(QSize(16, 16)))
        self.group_cmbx.setCurrentIndex(-1)
        self.group_chkl.setPixmap(self.no_icon.pixmap(QSize(16, 16)))
        self.mtpl_yesbt.setChecked(False)
        self.mtpl_nobt.setChecked(False)
        self.mtpl_chkl.setPixmap(self.no_icon.pixmap(QSize(16, 16)))
        self.myv_nobt.setChecked(False)
        self.myv_nobt.setChecked(False)
        self.myv_chkl.setPixmap(self.no_icon.pixmap(QSize(16, 16)))

    def clear_param_items(self):
        self.update_param_view()
        self.palias_le.clear()
        self.default_le.clear()
        self.default_chkl.setPixmap(self.no_icon.pixmap(QSize(16, 16)))
        self.unit_le.clear()
        self.guitype_cmbx.setCurrentIndex(-1)
        self.guitype_chkl.setPixmap(self.yes_icon.pixmap(QSize(16, 16)))
        self.param_setup_gbox.setEnabled(False)

    def func_item_selected(self, text):
        if text:
            self.current_function = text
            self.update_code_editor()
            self.update_func_setup()

            if any(
                [
                    self.current_function in str(x)
                    for x in self.add_pd_params["functions"]
                ]
            ):
                self.param_setup_gbox.setEnabled(True)
                self.update_param_view()
                self.current_parameter = self.add_pd_params.loc[
                    [
                        self.current_function in str(x)
                        for x in self.add_pd_params["functions"]
                    ]
                ].index[0]
                self.update_exst_param_label()
                self.update_param_setup()
            else:
                self.update_exst_param_label()
                # Clear existing entries
                self.clear_param_items()

    def param_item_selected(self, current):
        self.current_parameter = self.param_model.getData(current)
        self.update_param_setup()
        self.update_code_editor()

    def update_func_setup(self):
        if pd.notna(self.add_pd_funcs.loc[self.current_function, "alias"]):
            self.falias_le.setText(
                self.add_pd_funcs.loc[self.current_function, "alias"]
            )
        else:
            self.falias_le.clear()
        if pd.notna(self.add_pd_funcs.loc[self.current_function, "target"]):
            self.target_cmbx.setCurrentText(
                self.add_pd_funcs.loc[self.current_function, "target"]
            )
            self.target_chkl.setPixmap(self.yes_icon.pixmap(QSize(16, 16)))
        else:
            self.target_cmbx.setCurrentIndex(-1)
            self.target_chkl.setPixmap(self.no_icon.pixmap(QSize(16, 16)))
        if pd.notna(self.add_pd_funcs.loc[self.current_function, "tab"]):
            self.tab_cmbx.setCurrentText(
                self.add_pd_funcs.loc[self.current_function, "tab"]
            )
            self.tab_chkl.setPixmap(self.yes_icon.pixmap(QSize(16, 16)))
        else:
            self.tab_cmbx.setCurrentIndex(-1)
            self.tab_chkl.setPixmap(self.no_icon.pixmap(QSize(16, 16)))
        if pd.notna(self.add_pd_funcs.loc[self.current_function, "group"]):
            self.group_cmbx.setCurrentText(
                self.add_pd_funcs.loc[self.current_function, "group"]
            )
            self.group_chkl.setPixmap(self.yes_icon.pixmap(QSize(16, 16)))
        else:
            self.group_cmbx.setCurrentIndex(-1)
            self.group_chkl.setPixmap(self.no_icon.pixmap(QSize(16, 16)))
        if pd.notna(self.add_pd_funcs.loc[self.current_function, "matplotlib"]):
            if self.add_pd_funcs.loc[self.current_function, "matplotlib"]:
                self.mtpl_yesbt.setChecked(True)
            else:
                self.mtpl_nobt.setChecked(True)
            self.mtpl_chkl.setPixmap(self.yes_icon.pixmap(QSize(16, 16)))
        else:
            self.mtpl_void.setChecked(True)
            self.mtpl_chkl.setPixmap(self.no_icon.pixmap(QSize(16, 16)))
        if pd.notna(self.add_pd_funcs.loc[self.current_function, "mayavi"]):
            if self.add_pd_funcs.loc[self.current_function, "mayavi"]:
                self.myv_yesbt.setChecked(True)
            else:
                self.myv_nobt.setChecked(True)
            self.myv_chkl.setPixmap(self.yes_icon.pixmap(QSize(16, 16)))
        else:
            self.myv_void.setChecked(True)
            self.myv_chkl.setPixmap(self.no_icon.pixmap(QSize(16, 16)))

    def update_exst_param_label(self):
        if self.current_function:
            if len(self.param_exst_dict[self.current_function]) > 0:
                self.exstparam_l.setText(
                    f"Already existing Parameters: "
                    f"{self.param_exst_dict[self.current_function]}"
                )
                self.exstparam_l.show()
            else:
                self.exstparam_l.hide()

    def update_param_setup(self):
        if pd.notna(self.add_pd_params.loc[self.current_parameter, "alias"]):
            self.palias_le.setText(
                self.add_pd_params.loc[self.current_parameter, "alias"]
            )
        else:
            self.palias_le.clear()
        if pd.notna(self.add_pd_params.loc[self.current_parameter, "default"]):
            self.default_le.setText(
                self.add_pd_params.loc[self.current_parameter, "default"]
            )
            self.default_chkl.setPixmap(self.yes_icon.pixmap(QSize(16, 16)))
        else:
            self.default_le.clear()
            self.default_chkl.setPixmap(self.no_icon.pixmap(QSize(16, 16)))
        if pd.notna(self.add_pd_params.loc[self.current_parameter, "unit"]):
            self.unit_le.setText(self.add_pd_params.loc[self.current_parameter, "unit"])
        else:
            self.unit_le.clear()
        if pd.notna(self.add_pd_params.loc[self.current_parameter, "description"]):
            self.description_le.setText(
                self.add_pd_params.loc[self.current_parameter, "description"]
            )
        else:
            self.description_le.clear()
        if pd.notna(self.add_pd_params.loc[self.current_parameter, "gui_type"]):
            self.guitype_cmbx.setCurrentText(
                self.add_pd_params.loc[self.current_parameter, "gui_type"]
            )
            self.guitype_chkl.setPixmap(self.yes_icon.pixmap(QSize(16, 16)))
        else:
            self.guitype_cmbx.setCurrentIndex(-1)
            self.guitype_chkl.setPixmap(self.no_icon.pixmap(QSize(16, 16)))

    def check_func_setup(self):
        # Check, that all obligatory items of the Subject-Setup
        # and the Parameter-Setup are set.
        if all(
            [
                pd.notna(self.add_pd_funcs.loc[self.current_function, i])
                for i in self.oblig_func
            ]
        ):
            function_params = self.add_pd_params.loc[
                [
                    self.current_function in str(x)
                    for x in self.add_pd_params["functions"]
                ]
            ]
            if (
                pd.notna(
                    self.add_pd_params.loc[function_params.index, self.oblig_params]
                )
                .all()
                .all()
            ):
                self.func_chkl.setPixmap(self.yes_icon.pixmap(16, 16))
                self.add_pd_funcs.loc[self.current_function, "ready"] = 1
            else:
                self.func_chkl.setPixmap(self.no_icon.pixmap(16, 16))
                self.add_pd_funcs.loc[self.current_function, "ready"] = 0

    def update_param_view(self):
        # Update Param-Model with new pd_params of current_function
        current_pd_params = self.add_pd_params.loc[
            [self.current_function in str(x) for x in self.add_pd_params["functions"]]
        ]
        self.param_model.updateData(current_pd_params)

    def check_param_setup(self):
        # Check, that all obligatory items of the Parameter-Setup are set
        if all(
            [
                pd.notna(self.add_pd_params.loc[self.current_parameter, i])
                for i in self.oblig_params
            ]
        ):
            self.add_pd_params.loc[self.current_parameter, "ready"] = 1
        else:
            self.add_pd_params.loc[self.current_parameter, "ready"] = 0
        self.update_param_view()

    # Line-Edit Change-Signals
    def falias_changed(self, text):
        if self.current_function:
            self.add_pd_funcs.loc[self.current_function, "alias"] = text

    def mtpl_changed(self, current_button, state):
        if self.current_function:
            if state and current_button == self.mtpl_yesbt:
                self.add_pd_funcs.loc[self.current_function, "matplotlib"] = True
            elif state and current_button == self.mtpl_nobt:
                self.add_pd_funcs.loc[self.current_function, "matplotlib"] = False
            if current_button != self.mtpl_void:
                self.mtpl_chkl.setPixmap(self.yes_icon.pixmap(QSize(16, 16)))
            self.check_func_setup()

    def myv_changed(self, current_button, state):
        if self.current_function:
            if state and current_button == self.myv_yesbt:
                self.add_pd_funcs.loc[self.current_function, "mayavi"] = True
            elif state and current_button == self.myv_nobt:
                self.add_pd_funcs.loc[self.current_function, "mayavi"] = False
            if current_button != self.myv_void:
                self.myv_chkl.setPixmap(self.yes_icon.pixmap(QSize(16, 16)))
            self.check_func_setup()

    def palias_changed(self, text):
        if self.current_parameter:
            self.add_pd_params.loc[self.current_parameter, "alias"] = text

    def pdefault_changed(self, text):
        if self.current_parameter:
            self.add_pd_params.loc[self.current_parameter, "default"] = text
            self.default_chkl.setPixmap(self.yes_icon.pixmap(QSize(16, 16)))
            self.check_param_setup()
            self.check_func_setup()

    def punit_changed(self, text):
        if self.current_parameter:
            self.add_pd_params.loc[self.current_parameter, "unit"] = text

    def pdescription_changed(self, text):
        if self.current_parameter:
            self.add_pd_params.loc[self.current_parameter, "description"] = text

    def populate_target_cmbx(self):
        self.target_cmbx.insertItems(0, ["MEEG", "FSMRI", "Group", "Other"])

    def populate_tab_cmbx(self):
        self.tab_cmbx.clear()
        tab_set = set(self.ct.pd_funcs["tab"])
        tab_set2 = set(self.add_pd_funcs.loc[pd.notna(self.add_pd_funcs["tab"]), "tab"])
        self.tab_cmbx.insertItems(0, tab_set | tab_set2)

    def populate_group_cmbx(self):
        self.group_cmbx.clear()
        tab_set = set(self.ct.pd_funcs["group"])
        tab_set2 = set(
            self.add_pd_funcs.loc[pd.notna(self.add_pd_funcs["group"]), "group"]
        )
        self.group_cmbx.insertItems(0, tab_set | tab_set2)

    def populate_guitype_cmbx(self):
        self.guitype_cmbx.insertItems(0, self.available_param_guis)

    def target_cmbx_changed(self, idx):
        if self.current_function:
            self.add_pd_funcs.loc[self.current_function, "target"] = (
                self.target_cmbx.itemText(idx)
            )
            self.target_chkl.setPixmap(self.yes_icon.pixmap(QSize(16, 16)))
            self.check_func_setup()

    def tab_cmbx_changed(self, idx):
        # Insert changes from other functions if edited
        self.populate_tab_cmbx()
        self.tab_cmbx.setCurrentIndex(idx)
        if self.current_function:
            self.add_pd_funcs.loc[self.current_function, "tab"] = (
                self.tab_cmbx.itemText(idx)
            )
            self.tab_chkl.setPixmap(self.yes_icon.pixmap(QSize(16, 16)))
            self.check_func_setup()

    def tab_cmbx_edited(self, text):
        if self.current_function and text != "":
            self.add_pd_funcs.loc[self.current_function, "tab"] = text
            self.tab_chkl.setPixmap(self.yes_icon.pixmap(QSize(16, 16)))
            self.check_func_setup()

    def group_cmbx_changed(self, idx):
        # Insert changes from other functions if edited
        self.populate_group_cmbx()
        self.group_cmbx.setCurrentIndex(idx)
        group_name = self.group_cmbx.itemText(idx)
        if self.current_function:
            self.add_pd_funcs.loc[self.current_function, "group"] = group_name
            for param in self.add_pd_params.index:
                self.add_pd_params.loc[param, "group"] = group_name
            self.group_chkl.setPixmap(self.yes_icon.pixmap(QSize(16, 16)))
            self.check_func_setup()

    def group_cmbx_edited(self, text):
        if self.current_function and text != "":
            self.add_pd_funcs.loc[self.current_function, "group"] = text
            for param in self.add_pd_params.index:
                self.add_pd_params.loc[param, "group"] = text
            self.group_chkl.setPixmap(self.yes_icon.pixmap(QSize(16, 16)))
            self.check_func_setup()

    def guitype_cmbx_changed(self, idx):
        text = self.guitype_cmbx.itemText(idx)
        gui_args = {}
        options = []

        if self.current_parameter:
            # If ComboGui or CheckListGui, options have to be set:
            if text in ["ComboGui", "CheckListGui"]:
                # Check if options already in gui_args
                loaded_gui_args = self.add_pd_params.loc[
                    self.current_parameter, "gui_args"
                ]
                if pd.notna(loaded_gui_args):
                    gui_args = literal_eval(loaded_gui_args)
                    if "options" in gui_args:
                        options = gui_args["options"]

                ChooseOptions(self, text, options)

                # Save the gui_args in add_pd_params
                gui_args["options"] = options
                self.add_pd_params.loc[self.current_parameter, "gui_args"] = str(
                    gui_args
                )

            # Check, if default_value and gui_type match
            if pd.notna(self.add_pd_params.loc[self.current_parameter, "default"]):
                result, _ = self.test_param_gui(
                    default_string=self.add_pd_params.loc[
                        self.current_parameter, "default"
                    ],
                    gui_type=text,
                    gui_args=gui_args,
                )
            else:
                result = None

            if not result:
                self.add_pd_params.loc[self.current_parameter, "gui_type"] = text
                self.guitype_chkl.setPixmap(self.yes_icon.pixmap(QSize(16, 16)))
                self.check_param_setup()
                self.check_func_setup()
            else:
                self.guitype_cmbx.setCurrentIndex(-1)
                self.add_pd_params.loc[self.current_parameter, "gui_type"] = None
                self.check_param_setup()
                self.check_func_setup()

    def pguiargs_changed(self, gui_args):
        if self.current_parameter:
            # Check, if default_value and gui_type match
            if pd.notna(
                self.add_pd_params.loc[self.current_parameter, ["default", "gui_type"]]
            ).all():
                result, _ = self.test_param_gui(
                    default_string=self.add_pd_params.loc[
                        self.current_parameter, "default"
                    ],
                    gui_type=self.add_pd_params.loc[self.current_parameter, "gui_type"],
                    gui_args=gui_args,
                )
            else:
                result = None

            if not result:
                self.add_pd_params.loc[self.current_parameter, "gui_args"] = str(
                    gui_args
                )
            else:
                self.add_pd_params.loc[self.current_parameter, "gui_args"] = None

    def get_functions(self):
        # Clear Function- and Parameter-DataFrame
        self.add_pd_funcs.drop(index=self.add_pd_funcs.index, inplace=True)
        self.add_pd_params.drop(index=self.add_pd_funcs.index, inplace=True)
        self.clear_func_items()
        self.clear_param_items()

        # Returns tuple of files-list and file-type
        cf_path_string = compat.getopenfilename(
            self,
            "Choose the Python-File containing your function to import",
            filters="Python-File (*.py)",
        )[0]
        if cf_path_string:
            self.file_path = Path(cf_path_string)
            ImportFuncs(self)

    def edit_functions(self):
        # Clear Function- and Parameter-DataFrame
        self.add_pd_funcs.drop(index=self.add_pd_funcs.index, inplace=True)
        self.add_pd_params.drop(index=self.add_pd_funcs.index, inplace=True)
        self.clear_func_items()
        self.clear_param_items()

        # Returns tuple of files-list and file-type
        cf_path_string = compat.getopenfilename(
            self,
            "Choose the Python-File containing the functions to edit",
            filters="Python-File (*.py)",
            directory=self.ct.custom_pkg_path,
        )[0]
        if cf_path_string:
            self.file_path = Path(cf_path_string)
            ImportFuncs(self, edit_existing=True)

    def test_param_gui(self, default_string, gui_type, gui_args=None):
        # Test ParamGui with Value
        if gui_args is None:
            gui_args = {}
        test_parameters = {}
        try:
            test_parameters[self.current_parameter] = literal_eval(default_string)
        except (ValueError, SyntaxError):
            # Allow parameters to be defined by functions by numpy, etc.
            if self.add_pd_params.loc[self.current_parameter, "gui_type"] == "FuncGui":
                test_parameters[self.current_parameter] = eval(default_string)
            else:
                test_parameters[self.current_parameter] = default_string
        if pd.notna(self.add_pd_params.loc[self.current_parameter, "alias"]):
            alias = self.add_pd_params.loc[self.current_parameter, "alias"]
        else:
            alias = self.current_parameter
        if pd.notna(self.add_pd_params.loc[self.current_parameter, "description"]):
            description = self.add_pd_params.loc[self.current_parameter, "description"]
        else:
            description = None
        if pd.notna(self.add_pd_params.loc[self.current_parameter, "unit"]):
            unit = self.add_pd_params.loc[self.current_parameter, "unit"]
        else:
            unit = None

        gui_handle = getattr(parameter_widgets, gui_type)
        handle_params = inspect.signature(gui_handle).parameters
        try:
            if "unit" in handle_params:
                gui = gui_handle(
                    data=test_parameters,
                    name=self.current_parameter,
                    alias=alias,
                    description=description,
                    unit=unit,
                    **gui_args,
                )
            else:
                gui = gui_handle(
                    data=test_parameters,
                    name=self.current_parameter,
                    alias=alias,
                    description=description,
                    **gui_args,
                )
        except Exception as e:
            gui = None
            result = e
            QMessageBox.warning(
                self,
                "Error in ParamGui",
                f"The execution of {gui_type} with "
                f"{default_string} as default and "
                "{gui_args} as additional parameters raises"
                " the following error:\n"
                f"{result}",
            )
        else:
            result = None

        return result, gui

    def show_param_gui(self):
        if self.current_parameter and pd.notna(
            self.add_pd_params.loc[self.current_parameter, "gui_type"]
        ):
            TestParamGui(self)

    def update_code_editor(self):
        if self.code_editor:
            self.code_editor.clear()
            self.code_editor.insertPlainText(self.code_dict[self.current_function])

    def show_code(self):
        self.code_editor = CodeEditor(self, read_only=True)
        self.update_code_editor()
        code_dialog = SimpleDialog(
            self.code_editor, parent=self, modal=False, window_title="Source-Code"
        )
        set_ratio_geometry(0.5, code_dialog)
        center(code_dialog)

    def save_pkg(self):
        if any(self.add_pd_funcs["ready"] == 1):
            SavePkgDialog(self)

    def closeEvent(self, event):
        drop_funcs = [
            f for f in self.add_pd_funcs.index if not self.add_pd_funcs.loc[f, "ready"]
        ]

        if len(drop_funcs) > 0:
            answer = QMessageBox.question(
                self,
                "Close Custom-Functions?",
                f"There are still "
                f"unfinished functions:\n"
                f"{drop_funcs}\n"
                f"Do you still want to quit?",
            )
        else:
            answer = None

        if answer == QMessageBox.Yes or answer is None:
            event.accept()
        else:
            event.ignore()


class ChooseCustomModules(QDialog):
    def __init__(self, main_win):
        super().__init__(main_win)
        self.mw = main_win
        self.ct = main_win.ct
        self.modules = {
            pkg_name: self.ct.all_modules[pkg_name] for pkg_name in self.ct.all_modules
        }
        self.selected_modules = self.ct.get_setting("selected_modules")

        self.init_ui()
        self.open()

    def init_ui(self):
        self.layout = QVBoxLayout()

        tab_widget = QTabWidget()

        for pkg_name in self.modules:
            list_widget = CheckList(
                data=self.modules[pkg_name], checked=self.selected_modules
            )
            tab_widget.addTab(list_widget, pkg_name)

        self.layout.addWidget(tab_widget)

        close_bt = QPushButton("Close")
        close_bt.clicked.connect(self.close)
        self.layout.addWidget(close_bt)

        self.setLayout(self.layout)

    def closeEvent(self, event):
        self.ct.settings["selected_modules"] = self.selected_modules
        self.ct.import_custom_modules()
        self.mw.redraw_func_and_param()
        event.accept()


class AddKwargs(QDialog):
    def __init__(self, main_win):
        super().__init__(main_win)
        self.ct = main_win.ct
        self.current_func = None

        self.init_ui()
        self.open()

    def init_ui(self):
        layout = QVBoxLayout()

        list_layout = QHBoxLayout()
        func_list = CheckDictList(
            self.ct.pd_funcs.index, self.ct.pr.add_kwargs, no_bt="SP_MessageBoxQuestion"
        )
        func_list.currentChanged.connect(self.func_selected)
        list_layout.addWidget(func_list)

        self.kwarg_dict = EditDict(
            {}, title="Add Keyword-Arguments:", resize_rows=True, resize_columns=True
        )
        list_layout.addWidget(self.kwarg_dict)

        layout.addLayout(list_layout)

        close_bt = QPushButton("Close")
        close_bt.clicked.connect(self.close)
        layout.addWidget(close_bt)

        self.setLayout(layout)

    def _check_empty(self):
        """Check if the dict for current_func in add_kwargs is empty, then
        remove it."""
        if self.current_func:
            if self.current_func in self.ct.pr.add_kwargs:
                if len(self.ct.pr.add_kwargs[self.current_func]) == 0:
                    self.ct.pr.add_kwargs.pop(self.current_func)

    def func_selected(self, func_name):
        # Remove dict of previous selected func if empty
        self._check_empty()
        self.current_func = func_name
        # Add dict for func_name if not present
        if func_name not in self.ct.pr.add_kwargs:
            self.ct.pr.add_kwargs[func_name] = {}
        # Give reference to this dictionary to the DictModel
        self.kwarg_dict.replace_data(self.ct.pr.add_kwargs[func_name])

    def closeEvent(self, event):
        self._check_empty()
        event.accept()
