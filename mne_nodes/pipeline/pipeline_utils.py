"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import inspect
import logging
import multiprocessing
import os
import sys
from pathlib import Path

import psutil

from mne_nodes import ismac, iswin, islin


def get_n_jobs(n_jobs):
    """Get the number of jobs to use for parallel processing."""
    if n_jobs == -1 or n_jobs in ["auto", "max"]:
        n_cores = multiprocessing.cpu_count()
    else:
        n_cores = int(n_jobs)

    return n_cores


def compare_filep(obj, path, target_parameters=None, verbose=True):
    """Compare the parameters of the previous run to the current parameters for
    the given path.

    Parameters
    ----------
    obj : MEEG | FSMRI | Group
        A Data-Object to get the information needed
    path : str
        The path for the file to compare the parameters
    target_parameters : list | None
        The parameters to compare (set None for all)
    verbose : bool
        Set to True to print the outcome for each parameter to the console

    Returns
    -------
    result_dict : dict
        A dictionary with every parameter from target_parameters
        with a value as result:
            None, if nothing changed |
            tuple (previous_value, current_value, critical) |
            'missing', if path hasn't been saved yet
    """

    result_dict = {}
    file_name = Path(path).name
    # Try to get the parameters relevant for the last function,
    # which altered the data at path
    # The last entry in FUNCTION should be the most recent
    if not target_parameters:
        target_parameters = obj.params.keys()
    function_dict = obj.file_parameters.get(file_name, None)
    if function_dict is None:
        return {param: "missing" for param in target_parameters}
    function = function_dict["FUNCTION"]
    try:
        func_meta = obj.ct.get_meta(function)
    except KeyError:
        return {param: "missing" for param in target_parameters}
    critical_params = func_meta["parameters"]
    for param in target_parameters:
        try:
            previous_value = obj.file_parameters[file_name][param]
            current_value = obj.params[param]

            if str(previous_value) == str(current_value):
                result_dict[param] = "equal"
                if verbose:
                    logging.debug(f"{param} equal for {file_name}")
            else:
                if param in critical_params:
                    result_dict[param] = (previous_value, current_value, True)
                    if verbose:
                        logging.debug(
                            f"{param} changed from {previous_value} to "
                            f"{current_value} for {file_name} "
                            f"and is probably crucial for {function}"
                        )
                else:
                    result_dict[param] = (previous_value, current_value, False)
                    if verbose:
                        logging.debug(
                            f"{param} changed from {previous_value} to "
                            f"{current_value} for {file_name}"
                        )
        except KeyError:
            result_dict[param] = "missing"
            if verbose:
                logging.warning(f"{param} is missing in records for {file_name}")

    if obj.ct.settings.value("overwrite"):
        result_dict[param] = "overwrite"
        if verbose:
            logging.info(
                f"{file_name} will be overwritten anyway"
                f" because Overwrite=True (Settings)"
            )

    return result_dict


def check_kwargs(kwargs, function):
    kwargs = kwargs.copy()

    existing_kwargs = inspect.signature(function).parameters

    for kwarg in [k for k in kwargs if k not in existing_kwargs]:
        kwargs.pop(kwarg)

    return kwargs


def count_dict_keys(d, max_level=None):
    """Count the number of keys of a nested dictionary."""
    keys = 0
    for value in d.values():
        if isinstance(value, dict):
            if max_level is None:
                keys += count_dict_keys(value)
            elif max_level > 1:
                keys += count_dict_keys(value, max_level - 1)
            else:
                keys += 1
        else:
            keys += 1

    return keys


def shutdown():
    if iswin:
        os.system("shutdown /s")
    if islin:
        os.system("sudo shutdown now")
    if ismac:
        os.system("sudo shutdown -h now")


def restart_program():
    """Restarts the current program, with file objects and descriptors
    cleanup."""
    logging.info("Restarting")
    try:
        p = psutil.Process(os.getpid())
        for handler in p.open_files() + p.connections():
            os.close(handler.fd)
    except Exception as e:
        logging.error(e)

    python = sys.executable
    os.execl(python, python, *sys.argv)


def _get_func_param_kwargs(func, params):
    kwargs = {
        kwarg: params[kwarg] if kwarg in params else None
        for kwarg in inspect.signature(func).parameters
    }

    return kwargs


def is_test():
    if "PYTEST_CURRENT_TEST" in os.environ:
        return True
    return False


def _run_from_script():
    return "__main__.py" in sys.argv[0]


def change_file_section(file_path, section, new_content):
    """Modifies a specified section of a file with new content.

    This function reads a file and alters a defined range of lines, specified
    by the section parameter, with the provided new content. It then writes
    the modified lines back to the original file.

    Parameters
    ----------
    file_path : Path
        The path to the file to be modified.
    section : tuple[int, int]
        A tuple indicating the start and end line indices (0-based, inclusive of
        start and exclusive of end) defining the section of the file to be replaced.
    new_content : str
        The new string content to replace the specified section of the file.
    """
    with open(file_path) as file:
        lines = file.readlines()
    start, end = section
    lines[start:end] = new_content.splitlines(keepends=True)
    with open(file_path, "w") as file:
        file.writelines(lines)
