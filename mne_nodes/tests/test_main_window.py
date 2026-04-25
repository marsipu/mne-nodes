"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import json


from mne_nodes.gui.main_window import MainWindow
from mne_nodes.pipeline.io import type_json_hook


def test_app_start(ct, main_window):
    """Test the application startup process with a controller and main
    window."""
    # Ensure the main window is created and visibl
    assert main_window.isVisible()

    # Verify the controller is set in the main window
    # (works because fixtuure scope is function)
    assert main_window.ct == ct

    # test rename
    ct.name = "test2"
    assert main_window.ct.name == "test2"

    # add node
    epoch_node = main_window.viewer.add_function_node("epoch_raw")
    epoch_node.input(port_name="raw").connect_to(
        main_window.viewer.node(node_name="filter_data").output(port_name="raw")
    )

    # test proper closing
    config_path = ct.config_path
    ct.show_plots = False
    main_window.close()
    with open(config_path) as f:
        config = json.load(f, object_hook=type_json_hook)
        assert config["name"] == "test2"
        assert config["show_plots"] is False

    # test re-opening and loading config
    new_main_window = MainWindow(ct)
    assert new_main_window.isVisible()
    assert new_main_window.controller.name == "test2"
    assert new_main_window.controller.show_plots is False
    assert new_main_window.viewer.node(node_name="epoch_raw") is not None
