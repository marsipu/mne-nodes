"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

from mne_nodes.pipeline.pipeline_utils import change_file_section


def test_init(controller):
    assert controller.name == "test"
    # Test renaming the controller
    controller.name = "test2"
    assert controller.name == "test2", "Controller name should be updated to 'test2'"


def test_module_import(tmp_path, controller, test_module, test_script):
    # Assert basic modules are imported
    assert controller.modules.keys() == ["basic_operations", "basic_plot"]

    # Add a custom module
    controller.add_custom_module(test_module)
    assert "test" in controller._modules, "Custom module should be imported"

    # Test custom module reload
    original_func = controller.modules["test"].test_func1
    assert original_func(2) == 4, "Custom function should return correct value"

    # Modify the module source code
    func1_code, start, end = controller.get_function_code("func1")

    new_test_code = "def test_func1(a):\n    return a ** 3\n"
    change_file_section(test_script, (start, end), new_test_code)

    # Reload the modules
    controller.reload_modules()

    # Get a new reference to the function
    new_func = controller.modules["test"].test_func1
    print(f"New function: {new_func} at {id(new_func)}")
    assert new_func(2) == 8, "New function reference should return updated value"

    # Test insertion
