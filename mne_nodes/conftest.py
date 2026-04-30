"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import json
import os  # added
from os import mkdir
from os.path import isdir
from pathlib import Path

import numpy as np
import pytest

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

tiny_bids_root = Path(__file__).parent / "tests" / "tiny_bids"


@pytest.fixture
def settings(tmp_path):
    """Fixture to create Settings with a temporary settings directory."""
    from mne_nodes.pipeline.settings import Settings

    os.environ["MNENODES_SETTINGS_DIR"] = str(tmp_path)
    settings = Settings()
    return settings


# ToDo: Create a dummy function-configuration and parameterss
@pytest.fixture
def ct(tmp_path, monkeypatch, settings):
    """Fixture to create a Controller with temporary config, data and subjects
    directories."""
    from mne_nodes.pipeline.controller import Controller

    # Simulate user input
    def dummy_user_input(*args, **kwargs):
        # Set the controller name
        if kwargs["input_type"] == "string":
            return "test"
        # set the directory where to save the config-file
        elif kwargs["input_type"] == "folder":
            return tmp_path
        else:
            raise RuntimeError(
                f"Unknown input type: '{kwargs['input_type']}' for dummy function"
            )

    # Monkeypatch needs to be set on controller-module, since its already imported
    monkeypatch.setattr(
        "mne_nodes.pipeline.controller.ask_user_custom", lambda *args, **kwargs: True
    )
    monkeypatch.setattr(
        "mne_nodes.pipeline.controller.get_user_input", dummy_user_input
    )
    monkeypatch.setattr(
        "mne_nodes.pipeline.controller.raise_user_attention",
        lambda *args, **kwargs: None,
    )
    # add bids_root to settings
    settings.set("bids_root", tiny_bids_root)

    # Create Controller
    ct = Controller(settings=settings)
    ct.ensure_ready(required=("config_path",))

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
    in_node = viewer.add_input_node()
    func_node = viewer.add_function_node("filter_bandpass")

    # Establish connection
    in_node.output(port_name="eeg").connect_to(func_node.input(port_name="raw"))

    viewer.auto_layout_nodes()
    viewer.zoom_to_nodes()


def _add_complex_nodes(viewer):
    # Create nodes
    in_node = viewer.add_input_node()
    filter_node = viewer.add_function_node("filter_bandpass")
    epochs_node = viewer.add_function_node("create_epochs")
    evokeds_node = viewer.add_function_node("create_evokeds")
    plot_node = viewer.add_function_node("plot_evokeds")

    # Connect the nodes
    in_node.output(port_idx=0).connect_to(filter_node.input(port_name="raw"))
    filter_node.output(port_name="raw").connect_to(epochs_node.input(port_name="raw"))
    epochs_node.output(port_name="epochs").connect_to(
        evokeds_node.input(port_name="epochs")
    )
    evokeds_node.output(port_name="evokeds").connect_to(
        plot_node.input(port_name="evokeds")
    )

    # ToDo Next: Add source space nodes

    viewer.auto_layout_nodes()
    viewer.zoom_to_nodes()


@pytest.fixture
def nodeviewer(qtbot, ct):
    # Lazy import to avoid optional dependency issues when this fixture is unused
    from mne_nodes.gui.node.node_viewer import NodeViewer

    viewer = NodeViewer(ct)
    _add_nodes(viewer)
    qtbot.addWidget(viewer)

    return viewer


@pytest.fixture
def main_window(ct, qtbot):
    # Lazy import to avoid optional dependency issues when this fixture is unused
    from mne_nodes.gui.main_window import MainWindow

    mw = MainWindow(ct)
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


@pytest.fixture
def basic_functions():
    return (
        "def test_function(a, b=1, c='test', d=[1,2,3]):\n"
        "    '''\n"
        "    This is a test function that adds two numbers and has other types as args.\n"
        "    '''\n"
        "    result = a + b\n"
        "    print(f'Parameters: c={c}, d={d}')\n"
        "    return result\n\n"
        "def another_function(x, flag=True):\n"
        "    '''\n"
        "    This function multiplies x by 2 if flag is True, else by 3.\n"
        "    '''\n"
        "    if flag:\n"
        "        product = x * 2\n"
        "    else:\n"
        "        product = x * 3\n"
        "    return product\n"
    )


@pytest.fixture
def basic_functions_alt():
    return (
        "def test_function(a, b=1, c='test', d=[1,2,3], e={'a': 1}):\n"
        "    '''\n"
        "    This is a test function that adds two numbers and has other types as args.\n"
        "    '''\n"
        "    result = a + b\n"
        "    print(f'Parameters: c={c}, d={d}')\n"
        "    return result\n\n"
        "def another_function(x, flag=True):\n"
        "    '''\n"
        "    This function multiplies x by 2 if flag is True, else by 3.\n"
        "    '''\n"
        "    if flag:\n"
        "        product = x * 2\n"
        "    else:\n"
        "        product = x * 3\n"
        "    return product\n"
    )


@pytest.fixture
def test_function():
    return (
        "def complex_function(raw, highpass=1, lowpass=40):\n"
        "    '''\n"
        "    This is a filter function from mne.\n"
        "    '''\n"
        "    import mne\n\n"
        "    # Apply a bandpass filter to the raw data\n"
        "    raw = mne.filter.filter_data(raw.info['sfreq'], highpass, lowpass)\n"
        "    return raw\n"
    )
