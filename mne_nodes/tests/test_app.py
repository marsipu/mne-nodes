"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import json

from mne_nodes.pipeline.io import type_json_hook


def test_app_start(controller, main_window):
    """Test the application startup process with a controller and main
    window."""
    # Ensure the main window is created and visibl
    assert main_window.isVisible()

    # Verify the controller is set in the main window
    # (works because fixtuure scope is function)
    assert main_window.controller == controller

    # test rename
    controller.name = "test2"
    assert main_window.controller.name == "test2"

    # test proper closing
    config_path = controller.config_path
    controller.parameter_preset = "test_preset"
    main_window.close()
    with open(config_path) as f:
        config = json.load(f, object_hook=type_json_hook)
        assert config["name"] == "test2"
        assert config["parameter_preset"] == "test_preset"
