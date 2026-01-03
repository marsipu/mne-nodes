"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import json

from qtpy.QtWidgets import QMessageBox

from mne_nodes.pipeline.controller import Controller
from mne_nodes.pipeline.io import TypedJSONEncoder
from mne_nodes.pipeline.pipeline_utils import change_file_section


def test_init(controller):
    assert controller.name == "test"
    # Test renaming the controller
    controller.name = "test2"
    assert controller.name == "test2", "Controller name should be updated to 'test2'"
    # Test setting values in container attributes
    bad_channels = controller.get("bad_channels")
    bad_channels["test_subject"] = ["EEG 001", "EEG 002"]
    controller.set("bad_channels", bad_channels)
    assert "test_subject" in controller.get("bad_channels")
    # Test persistence for reloading
    config_path = controller.config_path
    controller.flush()
    controller2 = Controller(config_path=config_path)
    assert controller2.name == "test2"
    assert "test_subject" in controller.get("bad_channels")
    # Test parameter set
    controller.set_parameter("param1", 42, "test_func1")
    assert controller.parameter("param1", "test_func1") == 42, (
        "Parameter 'param1' should be set to 42"
    )


def test_module_import(tmp_path, controller, test_module_config, test_script):
    # ToDo Next: Fix get_function_code
    # Assert basic modules are imported
    assert list(controller.modules.keys()) == ["basic_operations", "basic_plot"]

    # Add a custom module
    controller.add_custom_module(test_module_config)
    assert "test_module" in controller.modules, "Custom module should be imported"

    # Test custom module reloadw
    original_func = controller.modules["test_module"].test_func1
    assert original_func(2) == 4, "Custom function should return correct value"

    # Modify the module source code
    func1_code, start, end = controller.get_function_code("test_func1")

    new_test_code = "def test_func1(a):\n    return a ** 3\n"
    change_file_section(test_script, (start, end), new_test_code)

    # Reload the modules
    controller.reload_modules()

    # Get a new reference to the function
    new_func = controller.modules["test_module"].test_func1
    print(f"New function: {new_func} at {id(new_func)}")
    assert new_func(2) == 8, "New function reference should return updated value"

    # Test insertion


def test_config_change(tmp_path, controller, monkeypatch):
    old_config_path = controller.config_path
    # Check controller change with other options
    new_config_path = tmp_path / "new_config.json"
    test_dict = {
        "name": "test2",
        "parameters": {"test_func1": {"param_a": 1, "param_b": 2}},
    }
    with open(new_config_path, "w") as f:
        json.dump(test_dict, f, indent=4, cls=TypedJSONEncoder)
    # Simulate input to new config-path
    # Create a new config-file?
    monkeypatch.setattr(
        "qtpy.QtWidgets.QMessageBox.question",
        lambda x, y, z, buttons: QMessageBox.StandardButton.No,
    )
    # Path to existing config-file
    monkeypatch.setattr(
        "qtpy.compat.getopenfilename", lambda x, y, filters: (new_config_path, True)
    )
    controller.config_path = None
    assert controller.name == "test2", "Controller name should be updated to 'test2'"
    assert controller.parameter("param_a", "test_func1") == 1, (
        "New parameter should be loaded from config"
    )
    # Add parameters for test
    controller.set_parameter("new_param", 42, "test_func1")
    assert controller.parameter("new_param", "test_func1") == 42, (
        "New parameter should be set"
    )
    controller.flush()
    # Change back to other controller
    controller.config_path = old_config_path
    assert controller.name == "test", "Controller name should be reverted to 'test'"
    assert "new_param" not in controller.get("parameters"), (
        "Parameters should be reverted on config change"
    )
    # Change again to new config
    controller.config_path = new_config_path
    assert controller.name == "test2", "Controller name should be updated to 'test2'"
    assert controller.parameter("param_b", "test_func1") == 2, (
        "New parameter should be set"
    )
    assert controller.parameter("new_param", "test_func1") == 42, (
        "New parameter should persist after config reload"
    )


# ToDo: add a test about accessing and modifying config from multiple processes without data loss or race conditions
