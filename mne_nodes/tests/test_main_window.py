"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import json
from pathlib import Path

import pytest
from qtpy.QtCore import QObject, QPointF, Qt, Signal

from mne_nodes.gui.main_window import MainWindow
from mne_nodes.pipeline.io import type_json_hook


def test_main_window_defers_viewer_load_until_controller_ready(settings, qtbot):
    """The main window should not load viewer nodes before the controller setup is finalized."""
    from pathlib import Path

    from mne_nodes.gui.main_window import MainWindow
    from mne_nodes.pipeline.controller import Controller

    controller = Controller(settings=settings)
    settings.set("bids_root", Path(__file__).parent / "tiny_bids")
    main_window = MainWindow(controller)
    qtbot.addWidget(main_window)

    assert main_window.viewer._input_node is None
    assert len(main_window.viewer.nodes) == 0

    main_window.finalize_controller_setup()
    assert main_window.viewer.input_node is not None
    assert main_window.viewer.input_node.scene() is main_window.viewer.scene()
    main_window.close()


def test_finalize_controller_setup_preserves_loaded_nodes(ct, main_window):
    """Finalization should not replace nodes already loaded by the controller."""
    ct.load(nodes=True)
    nodes = dict(main_window.viewer.nodes)
    main_window.finalize_controller_setup()

    assert main_window.viewer.nodes == nodes
    assert all(node.scene() is main_window.viewer.scene() for node in nodes.values())


def test_app_start(ct, main_window, qtbot):
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
    qtbot.addWidget(new_main_window)
    new_main_window.finalize_controller_setup()
    assert new_main_window.isVisible()
    assert new_main_window.controller.name == "test2"
    assert new_main_window.controller.get("show_plots") is False
    assert new_main_window.viewer.node(node_name="test_epochs") is not None


def test_controller_welcome_tour_starts_when_gui_ready(ct, main_window, monkeypatch):
    """The welcome tour should be triggered from the controller once the main window exists."""
    ct.settings.set("first_start", True)
    seen = {}

    class DummyTour(QObject):
        finished = Signal()

        def __init__(self, main_window, steps):
            super().__init__()
            seen["main_window"] = main_window
            seen["steps"] = steps

    monkeypatch.setattr(
        "mne_nodes.pipeline.controller.ask_user", lambda *args, **kwargs: True
    )
    monkeypatch.setattr(ct, "load_config", lambda path: path)
    monkeypatch.setattr("mne_nodes.gui.welcome_tour.WelcomeTour", DummyTour)

    ct.initialize_welcome_tour()

    assert ct.settings.get("first_start", True) is False
    assert seen["main_window"] is ct.main_window
    assert seen["steps"][0]["widget"] is ct.main_window.viewer
    assert seen["steps"][1]["widget"]() is ct.main_window.viewer.input_node


def test_welcome_tour_tracks_loaded_input_node(
    ct, main_window, monkeypatch, tmp_path, qtbot
):
    """Starting the real tour should highlight and follow the loaded input node."""
    monkeypatch.setattr(
        "mne_nodes.pipeline.controller.ask_user", lambda *args, **kwargs: True
    )

    ct.initialize_welcome_tour()
    tour = ct.welcome_tour
    try:
        ct.ensure_ready()
        main_window.finalize_controller_setup()
        node = main_window.viewer.input_node
        assert node.scene() is main_window.viewer.scene()
        tour.show_step(1)
        assert tour.steps[1]["widget"]() is node
        assert tour.overlay.highlight_path == tour.compute_highlight_path(node)

        before = tour.overlay.highlight_path.boundingRect()
        node.setPos(node.pos() + QPointF(60, 40))
        qtbot.waitUntil(
            lambda: tour.overlay.highlight_path == tour.compute_highlight_path(node)
        )
        assert tour.overlay.highlight_path.boundingRect() != before
    finally:
        tour.finish()


@pytest.mark.parametrize("create_new", [True, False])
def test_welcome_tour_finish_selects_user_pipeline(
    ct, main_window, monkeypatch, tmp_path, qtbot, create_new
):
    """Finish discards the demo without writing to the packaged configuration."""
    from mne_nodes.pipeline.controller import default_config

    packaged_config = Path(__file__).parents[1] / "extra" / "Welcome_pipeline.json"
    packaged_bytes = packaged_config.read_bytes()
    previous_config = ct.config_path
    user_config = tmp_path / "user_pipeline.json"
    if not create_new:
        user_config.write_text(
            json.dumps({**default_config, "name": "existing", "parameters": {"x": 2}}),
            encoding="utf-8",
        )
    monkeypatch.setattr(
        "mne_nodes.pipeline.controller.ask_user", lambda *args, **kwargs: True
    )
    ct.initialize_welcome_tour()
    tour = ct.welcome_tour
    demo_config = ct.config_path
    assert demo_config != packaged_config
    assert ct.settings.get("config_path") == previous_config
    ct.set("parameters", {"demo": True})
    ct.set("selected_inputs", {"subject": ["demo"]})
    ct.save_config()
    assert json.loads(demo_config.read_text(encoding="utf-8"))["parameters"] == {
        "demo": True
    }
    assert packaged_config.read_bytes() == packaged_bytes

    prompts = []

    def choose_pipeline(*args, **kwargs):
        prompts.append(kwargs["buttons"])
        assert ct.config_path is None
        assert not main_window.viewer.nodes
        assert not tour.overlay.isVisible()
        assert not tour.widget.isVisible()
        assert not demo_config.exists()
        return create_new

    monkeypatch.setattr(
        "mne_nodes.pipeline.controller.ask_user_custom", choose_pipeline
    )
    monkeypatch.setattr(
        ct, "_prompt_pipeline_path", lambda message: ("new", user_config)
    )
    monkeypatch.setattr(
        "mne_nodes.pipeline.controller.get_user_input",
        lambda *args, **kwargs: user_config,
    )
    qtbot.mouseClick(tour.widget.finish_btn, Qt.MouseButton.LeftButton)

    assert prompts == [("Create new", "Use existing")]
    assert ct.config_path == user_config
    assert ct.settings.get("config_path") == user_config
    assert ct.get("parameters") == ({} if create_new else {"x": 2})
    assert ct.get("selected_inputs") == {}
    assert ct.name == ("new" if create_new else "existing")
    assert main_window.viewer.input_node.scene() is main_window.viewer.scene()
    assert main_window.viewer.input_node is not tour._target
    main_window.close()
    assert packaged_config.read_bytes() == packaged_bytes
    assert user_config.is_file()


def test_welcome_tour_creation_and_connection_tasks(
    ct, main_window, monkeypatch, qtbot
):
    """The real tour waits for node creation and a compatible port connection."""
    monkeypatch.setattr(
        "mne_nodes.pipeline.controller.ask_user", lambda *args, **kwargs: True
    )
    ct.initialize_welcome_tour()
    tour = ct.welcome_tour
    completed = []
    tour.task_completed.connect(completed.append)
    viewer = main_window.viewer
    try:
        assert not viewer.function_nodes
        tour.show_step(2)
        assert not tour.widget.next_btn.isEnabled()
        node = viewer.add_function_node("test_filter")
        qtbot.waitUntil(lambda: tour.widget.next_btn.isEnabled())
        assert completed == [2]
        tour.next_step()
        assert tour._target is node
        tour.next_step()
        assert tour.index == 4
        assert not tour.widget.next_btn.isEnabled()

        output = viewer.input_node.output(port_name="eeg")
        input_port = node.input(port_name="raw")
        output.connect_to(input_port)
        qtbot.waitUntil(lambda: tour.widget.next_btn.isEnabled())
        assert completed == [2, 4]
        output.disconnect_from(input_port)
        qtbot.waitUntil(lambda: not tour.widget.next_btn.isEnabled())
        output.connect_to(input_port)
        qtbot.waitUntil(lambda: tour.widget.next_btn.isEnabled())
        tour.next_step()
        assert tour.index == 5
        assert tour._target is node.param_box.graphicsProxyWidget()
        assert tour.overlay.highlight_path == tour.compute_highlight_path(tour._target)
        tour.next_step()
        assert tour._target is viewer.input_node.start_button_proxy
    finally:
        tour.finish()


def test_closing_welcome_tour_does_not_save_packaged_pipeline(
    ct, main_window, monkeypatch
):
    """Closing the application during the tour saves only its disposable copy."""
    packaged_config = Path(__file__).parents[1] / "extra" / "Welcome_pipeline.json"
    packaged_bytes = packaged_config.read_bytes()
    previous_config = ct.config_path
    monkeypatch.setattr(
        "mne_nodes.pipeline.controller.ask_user", lambda *args, **kwargs: True
    )
    ct.initialize_welcome_tour()
    ct.set("parameters", {"demo": True})
    main_window.close()
    assert packaged_config.read_bytes() == packaged_bytes
    assert ct.settings.get("config_path") == previous_config
    ct.welcome_tour.finished.disconnect(ct._finish_welcome_tour)
    ct.welcome_tour.finish()
    ct._welcome_config_directory.cleanup()


def test_window_registry_lookup_and_replacement(settings, qtbot):
    """Closing an older window must not unregister its replacement."""
    from mne_nodes.gui.widget_registry import get_widget
    from mne_nodes.pipeline.controller import Controller

    controller = Controller(settings=settings)
    old_window = MainWindow(controller)
    qtbot.addWidget(old_window)
    assert controller.main_window is old_window
    assert controller.viewer is old_window.viewer

    replacement = MainWindow(controller)
    qtbot.addWidget(replacement)
    old_window.close()
    assert controller.main_window is replacement
    assert controller.viewer is replacement.viewer

    replacement.close()
    assert get_widget("main_window") is None
    assert controller.viewer is None
