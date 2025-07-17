"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import json
import math
import os
import re
import subprocess
import sys
from ast import literal_eval
from inspect import getsource
from os.path import isdir, join, isfile

from mne_nodes.basic_functions import basic_operations, basic_plot
from mne_nodes.pipeline.loading import MEEG, FSMRI, Group
from mne_nodes.pipeline.pipeline_utils import type_json_hook, logger

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
    """This function checks for recent package changes and offers installation or manual
    installation instructions."""
    # For testing purposes
    if test_package is not None:
        new_packages[test_package] = test_package

    for import_name, install_name in new_packages.items():
        try:
            __import__(import_name)
        except ImportError:
            print(f"The package {import_name} " f"is required for this application.\n")
            ans = input("Do you want to install the " "new package now? [y/n]").lower()
            if ans == "y":
                try:
                    install_package(install_name)
                except subprocess.CalledProcessError:
                    logger().critical("Installation failed!")
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
    """Convert pandas DataFrames to a dictionary structure for function and parameter
    configuration."""
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

            module_dict["parameters"][param_name] = eval_dict
        configs[module_name] = module_dict

    return configs
