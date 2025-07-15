# -*- coding: utf-8 -*-
"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""
import json
from os import mkdir
from pathlib import Path

import pytest

from mne_nodes.gui.main_window import MainWindow
from mne_nodes.gui.node.node_viewer import NodeViewer
from mne_nodes.gui.node.nodes import FunctionNode
from mne_nodes.pipeline.controller import Controller


@pytest.fixture
def controller(tmpdir):
    # Create a config_file, meeg_root and fsmri_root
    config_path = Path(tmpdir.join("test_config.json"))
    with open(config_path, "w") as f:
        json.dump({"name": "test_controller"}, f, indent=4)
    meeg_root = Path(tmpdir.join("MEEG"))
    mkdir(meeg_root)
    fsmri_root = Path(tmpdir.join("FSMRI"))
    mkdir(fsmri_root)
    # Create Controller
    ct = Controller(config_path, meeg_root, fsmri_root)

    return ct


@pytest.fixture
def main_window(controller, qtbot):
    mw = MainWindow(controller)
    qtbot.addWidget(mw)

    return mw


@pytest.fixture
def parameter_values():
    """Fixture to provide a dictionary of parameter values."""
    return {
        "int": 1,
        "float": 5.3,
        "string": "postcentral-lh",
        "multi_type": 42,
        "func": "np.arange(10) * np.pi",
        "bool": True,
        "tuple": (45, 6),
        "combo": "b",
        "list": [1, 454.33, "postcentral-lh", 5],
        "check_list": ["postcentral-lh"],
        "dict": {"A": "B", "C": 58.144, 3: [1, 2, 3, 4], "D": {"A": 1, "B": 2}},
        "slider": 5,
        "color": {"C": "#98765432", "3": "#97867564"},
        "path": "C:/test",
    }


@pytest.fixture
def parameter_values_alt():
    """Fixture to provide alternative parameter values."""
    return {
        "int": 5,
        "float": 8.45,
        "string": "precentral-lh",
        "multi_type": 32,
        "func": "np.ones((2,3))",
        "bool": False,
        "tuple": (2, 23),
        "combo": "c",
        "list": [33, 2234.33, "precentral-lh", 3],
        "check_list": ["precentral-lh"],
        "dict": {"B": "V", "e": 11.333, 5: [65, 3, 11], "F": {"C": 1, "D": 2}},
        "slider": 2,
        "color": {"A": "#12345678", "B": "#13243546"},
        "path": "D:/test",
    }


@pytest.fixture
def nodeviewer(qtbot, controller):
    viewer = NodeViewer(controller, debug_mode=True)
    viewer.resize(1000, 1000)
    qtbot.addWidget(viewer)
    viewer.show()

    func_kwargs = {
        "ports": [
            {
                "name": "In1",
                "port_type": "in",
                "accepted_ports": ["Out1"],
            },
            {
                "name": "In2",
                "port_type": "in",
                "accepted_ports": ["Out1, Out2"],
            },
            {
                "name": "Out1",
                "port_type": "out",
                "accepted_ports": ["In1"],
                "multi_connection": True,
            },
            {
                "name": "Out2",
                "port_type": "out",
                "accepted_ports": ["In1", "In2"],
                "multi_connection": True,
            },
        ],
        "name": "test_func",
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
    }
    func_node1 = FunctionNode(controller, **func_kwargs)
    viewer.add_node(func_node1)
    func_node2 = FunctionNode(controller, **func_kwargs)
    viewer.add_node(func_node2)
    func_node1.output(port_idx=0).connect_to(func_node2.input(port_idx=0))

    func_node2.setPos(400, 100)

    return viewer


@pytest.fixture
def custom_module(tmpdir):
    pkg_path = tmpdir.join("test_module")
    mkdir(pkg_path)
    # Generate test Code
    test_code = "def test_func(a):\n    return a ** 2\n"
    with open(pkg_path.join("test.py"), "w") as f:
        f.write(test_code)
    # Generate test configuration file
    test_config = {
        "module_name": "test_module",
        "module_alias": "test_module",
        "functions": {
            "test_func": {
                "alias": "test_func",
                "group": "Test",
                "module": "test_module",
                "thread-safe": True,
                "plot": False,
                "inputs": ["a"],
                "outputs": ["a_squared"],
            }
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
            }
        },
    }
    test_config_path = Path(pkg_path.join("test_config.json"))
    with open(test_config_path, "w") as f:
        json.dump(test_config, f, indent=4)

    return test_config_path
