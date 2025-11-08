"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import json
import os  # added
from os import mkdir
from os.path import isdir
from pathlib import Path

import numpy as np
import pytest
from qtpy.QtWidgets import QMessageBox

# Force debug mode for all tests
os.environ["MNENODES_DEBUG"] = "true"


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
    "check_list": ["postcentral-lh", "insula-lh"],
    "dict": {"A": "B", "C": 58.144, "D": [1, 2, 3, 4], "E": {"A": 1, "B": 2}, 1: 123},
    "slider": 5,
    "color": {"C": "#98765432", 3: "#97867564"},
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
    "check_list": ["precentral-lh", "insula-rh"],
    "dict": {"B": "V", "e": 11.333, 5: [65, 3, 11], "F": {"C": 1, "D": 2}, 2: 456},
    "slider": 2,
    "color": {"A": "#12345678", "B": "#13243546"},
    "path": Path().home() / "test_path",
}


@pytest.fixture
def controller(tmp_path, monkeypatch):
    """Fixture to create a Controller with temporary config, data and subjects
    directories."""
    from mne_nodes.pipeline.controller import Controller

    # Create a config_file, data_path and subjects_dir
    controller_name = "test"
    data_path = tmp_path / "MEEG"
    mkdir(data_path)
    subjects_dir = tmp_path / "FSMRI"
    mkdir(subjects_dir)
    # Monkeypatching to simulate user input
    # Create a new config-file with answering yes
    monkeypatch.setattr(
        "qtpy.QtWidgets.QMessageBox.question",
        lambda x, y, z, buttons: QMessageBox.StandardButton.Yes,
    )
    # Set the controller name
    monkeypatch.setattr(
        "qtpy.QtWidgets.QInputDialog.getText", lambda x, y, z: (controller_name, True)
    )
    # set the directory where to save the config-file
    monkeypatch.setattr("qtpy.compat.getexistingdirectory", lambda x, y: tmp_path)
    # Create Controller
    ct = Controller()
    ct.data_path = data_path
    ct.subjects_dir = subjects_dir

    return ct


@pytest.fixture
def parameter_values():
    """Fixture to provide a dictionary of parameter values."""
    return test_parameters


@pytest.fixture
def parameter_values_alt():
    """Fixture to provide alternative parameter values."""
    return alternative_test_parameters


def _add_nodes(viewer):
    # Create nodes
    in_node = viewer.add_input_node("raw")
    func_node = viewer.add_function_node("filter_data")

    # Establish connection
    in_node.output(port_name="raw").connect_to(func_node.input(port_name="raw"))

    viewer.auto_layout_nodes()
    viewer.zoom_to_nodes()


def _add_complex_nodes(viewer):
    # Create nodes
    in_node = viewer.add_input_node("raw")
    func_node = viewer.add_function_node("filter_data")

    # Establish connection
    in_node.output(port_name="raw").connect_to(func_node.input(port_name="raw"))

    # Add more function nodes
    func_node2 = viewer.add_function_node("find_events")
    func_node3 = viewer.add_function_node("epoch_raw")
    func_node4 = viewer.add_function_node("plot_epochs")

    # Connect the nodes
    viewer.input_node("raw").output(port_name="raw").connect_to(
        func_node2.input(port_name="raw")
    )
    viewer.function_node("filter_data").output(port_name="raw").connect_to(
        func_node3.input(port_name="raw")
    )
    func_node2.output(port_name="events").connect_to(
        func_node3.input(port_name="events")
    )
    func_node3.output(port_name="epochs").connect_to(
        func_node4.input(port_name="epochs")
    )
    # ToDo: extend with fsmri-nodes and assignment nodes
    viewer.auto_layout_nodes()
    viewer.zoom_to_nodes()


@pytest.fixture
def nodeviewer(qtbot, controller):
    # Lazy import to avoid optional dependency issues when this fixture is unused
    from mne_nodes.gui.node.node_viewer import NodeViewer

    viewer = NodeViewer(controller)
    _add_nodes(viewer)
    qtbot.addWidget(viewer)

    return viewer


@pytest.fixture
def main_window(controller, qtbot):
    # Lazy import to avoid optional dependency issues when this fixture is unused
    from mne_nodes.gui.main_window import MainWindow

    mw = MainWindow(controller)
    _add_nodes(mw.viewer)
    qtbot.addWidget(mw)

    return mw


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
    test_module_path = tmp_path / "test_package"
    if not isdir(test_module_path):
        mkdir(test_module_path)
    test_script_path = test_module_path / "test_module.py"
    with open(test_script_path, "w") as f:
        f.write(test_code)

    return test_script_path


@pytest.fixture
def test_module_config(tmp_path, test_script):
    """Fixture to create a temporary JSON configuration file for the test
    module."""
    from mne_nodes.pipeline.io import TypedJSONEncoder

    # Generate test configuration file
    test_config = {
        "module_name": "test_module",
        "module_alias": "test_module",
        "functions": {
            "test_func1": {
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
                "min_val": 0,
            },
            "b": {
                "alias": "B",
                "Group": "Test",
                "default": 3,
                "unit": "s",
                "description": "This is another test parameter",
                "gui": "FloatGui",
                "min_val": 0.0,
            },
        },
    }
    test_config_path = test_script.parent / "test_module_config.json"
    with open(test_config_path, "w") as f:
        json.dump(test_config, f, indent=4, cls=TypedJSONEncoder)

    return test_config_path
