"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import json

from mne_nodes.gui.main_window import MainWindow
from mne_nodes.pipeline.io import type_json_hook


def test_main_window_defers_viewer_load_until_controller_ready(settings):
    """The main window should not load viewer nodes before the controller setup is finalized."""
    from pathlib import Path

    from mne_nodes.gui.main_window import MainWindow
    from mne_nodes.pipeline.controller import Controller

    controller = Controller(settings=settings)
    settings.set("bids_root", Path(__file__).parent / "tests" / "tiny_bids")
    main_window = MainWindow(controller)

    assert main_window.viewer.input_node is None
    assert len(main_window.viewer.nodes) == 0

    main_window.finalize_controller_setup()
    main_window.close()


def test_app_start(ct, main_window):
    """Test the application startup process with a controller and main
    window."""
    # Ensure the main window is created and visibl
    assert main_window.isVisible()

    # Verify the controller is set in the main window
    # (works because fixtuure scope is function)
    assert main_window.controller == ct

    # test rename
    ct.name = "test2"
    assert main_window.controller.name == "test2"

    # add node
    epoch_node = main_window.viewer.add_function_node("test_epochs")
    epoch_node.input(port_name="raw").connect_to(
        main_window.viewer.node(node_name="test_filter").output(port_name="raw")
    )

    # test proper closing
    config_path = ct.config_path
    ct.set("show_plots", False)
    main_window.close()
    with open(config_path) as f:
        config = json.load(f, object_hook=type_json_hook)
        assert config["name"] == "test2"
        assert config["show_plots"] is False

    # test re-opening and loading config
    new_main_window = MainWindow(ct)
    new_main_window.finalize_controller_setup()
    assert new_main_window.isVisible()
    assert new_main_window.controller.name == "test2"
    assert new_main_window.controller.get("show_plots") is False
    assert new_main_window.viewer.node(node_name="test_epochs") is not None


def test_controller_welcome_tour_starts_when_gui_ready(ct, monkeypatch):
    """The welcome tour should be triggered from the controller once the main window exists."""
    import mne_nodes

    ct.settings.set("first_start", True)
    seen = {}

    class DummyTour:
        def __init__(self, main_window, steps):
            seen["main_window"] = main_window
            seen["steps"] = steps

    monkeypatch.setattr(
        "mne_nodes.pipeline.controller.ask_user", lambda *args, **kwargs: True
    )
    monkeypatch.setitem(mne_nodes._widgets, "main_window", ct.main_window)
    monkeypatch.setattr("mne_nodes.gui.welcome_tour.WelcomeTour", DummyTour)

    ct.initialize_welcome_tour()

    assert ct.settings.get("first_start", True) is False
    assert seen["main_window"] is ct.main_window
    assert seen["steps"][0]["widget"] is ct.main_window.viewer.input_node
