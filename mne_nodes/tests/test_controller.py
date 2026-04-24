"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import json


from mne_nodes.pipeline.controller import Controller
from mne_nodes.pipeline.io import TypedJSONEncoder
from mne_nodes.pipeline.pipeline_utils import change_file_section


def test_init(ct):
    assert ct.name == "test"
    # Test renaming the controller
    ct.name = "test2"
    assert ct.name == "test2", "Controller name should be updated to 'test2'"
    # Test setting values in container attributes
    bad_channels = ct.get("bad_channels")
    bad_channels["test_subject"] = ["EEG 001", "EEG 002"]
    ct.set("bad_channels", bad_channels)
    assert "test_subject" in ct.get("bad_channels")
    # Test persistence for reloading
    config_path = ct.config_path
    ct.flush()
    controller2 = Controller(config_path=config_path)
    assert controller2.name == "test2"
    assert "test_subject" in ct.get("bad_channels")
    # Test parameter set
    ct.set_parameter("param1", 42, "test_func1")
    assert ct.parameter("param1", "test_func1") == 42, (
        "Parameter 'param1' should be set to 42"
    )


def test_module_import(tmp_path, ct, test_module_config, test_script):
    # ToDo Next: Fix get_function_code
    # Assert basic modules are imported
    assert list(ct.modules.keys()) == ["basic_operations", "basic_plot"]

    # Add a custom module
    ct.add_module(test_module_config)
    assert "test_module" in ct.modules, "Custom module should be imported"

    # Test custom module reloadw
    original_func = ct.modules["test_module"].test_func1
    assert original_func(2) == 4, "Custom function should return correct value"

    # Modify the module source code
    func1_code, start, end = ct.get_function_code("test_func1")

    new_test_code = "def test_func1(a):\n    return a ** 3\n"
    change_file_section(test_script, (start, end), new_test_code)

    # Reload the modules
    ct.reload_modules()

    # Get a new reference to the function
    new_func = ct.modules["test_module"].test_func1
    print(f"New function: {new_func} at {id(new_func)}")
    assert new_func(2) == 8, "New function reference should return updated value"

    # Test insertion


def test_config_change(tmp_path, ct, monkeypatch):
    old_config_path = ct.config_path
    # Check controller change with other options
    new_config_path = tmp_path / "new_config.json"
    test_dict = {
        "name": "test2",
        "parameters": {"test_func1": {"param_a": 1, "param_b": 2}},
    }
    with open(new_config_path, "w") as f:
        json.dump(test_dict, f, indent=4, cls=TypedJSONEncoder)
    # Simulate input to new config-path
    # Create a new config-file? Use existing!
    monkeypatch.setattr(
        "mne_nodes.pipeline.controller.ask_user_custom", lambda *a, **k: False
    )
    # Path to existing config-file
    monkeypatch.setattr(
        "mne_nodes.pipeline.controller.get_user_input", lambda *a, **k: new_config_path
    )
    ct.config_path = None
    assert ct.name == "test2", "Controller name should be updated to 'test2'"
    assert ct.parameter("param_a", "test_func1") == 1, (
        "New parameter should be loaded from config"
    )
    # Add parameters for test
    ct.set_parameter("new_param", 42, "test_func1")
    assert ct.parameter("new_param", "test_func1") == 42, "New parameter should be set"
    ct.flush()
    # Change back to other controller
    ct.config_path = old_config_path
    assert ct.name == "test", "Controller name should be reverted to 'test'"
    assert "new_param" not in ct.get("parameters"), (
        "Parameters should be reverted on config change"
    )
    # Change again to new config
    ct.config_path = new_config_path
    assert ct.name == "test2", "Controller name should be updated to 'test2'"
    assert ct.parameter("param_b", "test_func1") == 2, "New parameter should be set"
    assert ct.parameter("new_param", "test_func1") == 42, (
        "New parameter should persist after config reload"
    )


# ToDo: add a test about accessing and modifying config from multiple processes without data loss or race conditions
