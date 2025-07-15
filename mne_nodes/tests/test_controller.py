# -*- coding: utf-8 -*-
"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""
from importlib import import_module
from os.path import join, isfile

from PySide6.QtWidgets import QMessageBox

from mne_nodes.pipeline.controller import Controller


# ToDo Next: Make this test run
def test_init(monkeypatch, tmpdir):

    monkeypatch.setattr(
        "qtpy.QtWidgets.QMessageBox.question",
        lambda x, y, z: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        "qtpy.QtWidgets.QInputDialog.getText", lambda x, y, z: ("test", True)
    )
    monkeypatch.setattr(
        "qtpy.QtWidgets.QFileDialog.getExistingDirectory", lambda x, y: tmpdir
    )

    # Initialize the controller in gui mode
    Controller()

    # Initialize another controller with the new config-file
    controller = Controller(config_path=join(tmpdir, "test_config.json"))

    # Test renaming the controller
    controller.name = "test2"
    assert controller.name == "test2", "Controller name should be updated to 'test2'"
    assert isfile(join(tmpdir, "test2_config.json")), "Config file should be renamed"

    # ToDo: Test initialization of the controller in headless mode


def test_module_import(tmpdir, controller, custom_module):
    # Assert basic modules are imported
    assert controller._basic_module_list == list(
        controller._modules.keys()
    ), "Basic modules should be imported"

    # Add a custom module
    controller.config["custom_module_meta"] = {"test": custom_module}
    controller.load_custom_modules()
    assert "test" in controller._modules, "Custom module should be imported"

    # Test custom module reload
    original_func = controller.modules["test"].test_func
    print(f"Original function: {original_func} at {id(original_func)}")
    assert original_func(2) == 4, "Custom function should return correct value"

    # Modify the module source code
    test_script_path = join(tmpdir, "test_module", "test.py")
    new_test_code = "def test_func(a):\n    return a ** 3\n"
    with open(test_script_path, "w") as f:
        f.write(new_test_code)

    # Reload the modules
    controller.reload_modules()

    # Get a new reference to the function
    new_func = controller.modules["test"].test_func
    print(f"New function: {new_func} at {id(new_func)}")
    assert new_func(2) == 8, "New function reference should return updated value"

