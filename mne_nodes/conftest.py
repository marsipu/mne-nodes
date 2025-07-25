"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import json
from os import mkdir
from os.path import isdir
from pathlib import Path

import numpy as np
import pytest

from mne_nodes.__main__ import init_logging
from mne_nodes.gui.main_window import MainWindow
from mne_nodes.gui.node.node_viewer import NodeViewer
from mne_nodes.pipeline.controller import Controller

# Initialize logging for tests
init_logging(debug_mode=True)

test_parameters = {
    "int": 2,
    "float": 5.3,
    "string": "postcentral-lh",
    "multi_type": 42,
    "func": np.arange(10) * np.pi,
    "func_exp": "np.arange(10) * np.pi",
    "bool": True,
    "tuple": (3.4, 5),
    "combo": "b",
    "list": [1, 454.33, "postcentral-lh", True],
    "check_list": ["postcentral-lh"],
    "dict": {"A": "B", "C": 58.144, "D": [1, 2, 3, 4], "E": {"A": 1, "B": 2}},
    "slider": 5,
    "color": {"C": "#98765432", "3": "#97867564"},
    "path": Path().home(),
}

alternative_test_parameters = {
    "int": 5,
    "float": 8.45,
    "string": "precentral-lh",
    "multi_type": 32,
    "func": np.ones((2, 3)),
    "func_exp": "np.ones((2,3))",
    "bool": False,
    "tuple": (2, 55.1),
    "combo": "c",
    "list": [33, 2234.33, "precentral-lh", False],
    "check_list": ["precentral-lh"],
    "dict": {"B": "V", "e": 11.333, 5: [65, 3, 11], "F": {"C": 1, "D": 2}},
    "slider": 2,
    "color": {"A": "#12345678", "B": "#13243546"},
    "path": Path().home() / "test_path",
}


@pytest.fixture
def controller(tmp_path):
    # Create a config_file, data_path and subjects_dir
    config_path = tmp_path / "test_config.json"
    with open(config_path, "w") as f:
        json.dump({"name": "test_controller"}, f, indent=4)
    data_path = tmp_path / "MEEG"

    mkdir(data_path)
    subjects_dir = tmp_path / "FSMRI"
    mkdir(subjects_dir)
    # Create Controller
    ct = Controller(config_path, data_path, subjects_dir)

    return ct


@pytest.fixture
def main_window(controller, qtbot):
    mw = MainWindow(controller)
    qtbot.addWidget(mw)

    return mw


@pytest.fixture
def parameter_values():
    """Fixture to provide a dictionary of parameter values."""
    return test_parameters


@pytest.fixture
def parameter_values_alt():
    """Fixture to provide alternative parameter values."""
    return alternative_test_parameters


@pytest.fixture
def nodeviewer(qtbot, controller):
    viewer = NodeViewer(controller, debug_mode=True)
    viewer.resize(1000, 1000)
    qtbot.addWidget(viewer)
    viewer.show()

    # Create nodes
    in_node = viewer.add_input_node("raw")
    func_node1 = viewer.add_function_node("find_bads")
    func_node2 = viewer.add_function_node("find_events")
    func_node3 = viewer.add_function_node("epoch_raw")
    func_node4 = viewer.add_function_node("plot_epochs")

    in_node.output("raw").connect_to(func_node1.input("raw"))
    in_node.output("raw").connect_to(func_node2.input("raw"))
    func_node1.output("raw").connect_to(func_node3.input("raw"))
    func_node2.output("events").connect_to(func_node3.input("events"))
    func_node3.output("epochs").connect_to(func_node4.input("epochs"))

    return viewer


@pytest.fixture
def test_code():
    """Fixture to provide a simple test code."""
    return (
        "def test_func1(a):\n    "
        "print('This is a test function')\n    "
        "return a ** 2\n"
        "\n"
        "def test_func2(b):\n    "
        "print('This is another test function')\n    "
        "return b + 1\n"
        "\n"
    )


@pytest.fixture
def test_script(tmp_path, test_code):
    """Fixture to create a temporary Python script with test code."""
    test_module_path = tmp_path / "test_module"
    if not isdir(test_module_path):
        mkdir(test_module_path)
    test_script_path = test_module_path / "test.py"
    with open(test_script_path, "w") as f:
        f.write(test_code)

    return test_script_path


@pytest.fixture
def test_module(tmp_path, test_script):
    # Generate test configuration file
    test_config = {
        "module_name": "test_module",
        "module_alias": "test_module",
        "functions": {
            "test_func": {
                "alias": "test_func1",
                "group": "Test",
                "module": "test_module",
                "thread-safe": True,
                "plot": False,
                "inputs": ["a"],
                "outputs": ["a_squared"],
            },
            "test_func2": {
                "alias": "test_func2",
                "group": "Test",
                "module": "test_module",
                "thread-safe": True,
                "plot": False,
                "inputs": ["b"],
                "outputs": ["b_plus_one"],
            },
        },
        "parameters": {
            "a": {
                "alias": "A",
                "Group": "Test",
                "default": 2,
                "unit": "s",
                "description": "This is a test parameter",
                "gui": "IntGui",
                "gui_args": {"min_val": 0},
            },
            "b": {
                "alias": "B",
                "Group": "Test",
                "default": 3,
                "unit": "s",
                "description": "This is another test parameter",
                "gui": "FloatGui",
                "gui_args": {"min_val": 0.0},
            },
        },
    }
    test_config_path = test_script.parent / "test_config.json"
    with open(test_config_path, "w") as f:
        json.dump(test_config, f, indent=4)

    return test_config_path
