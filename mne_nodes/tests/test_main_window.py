"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import json
from pathlib import Path

import pytest
from qtpy.QtCore import QObject, QPointF, Qt, Signal
from qtpy.QtGui import QContextMenuEvent
from qtpy.QtTest import QTest
from qtpy.QtWidgets import QMenu, QStyle, QStyleOptionViewItem

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

        def finish(self, *, notify=True):
            pass

    monkeypatch.setattr(
        "mne_nodes.gui.welcome_tour.ask_user", lambda *args, **kwargs: True
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
        "mne_nodes.gui.welcome_tour.ask_user", lambda *args, **kwargs: True
    )

    ct.initialize_welcome_tour()
    tour = ct.welcome_tour
    assert "example_function" in ct.plugins
    assert "example_filter" in ct.function_meta
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


def test_welcome_tour_does_not_inherit_previous_input_selection(
    ct, main_window, monkeypatch
):
    """New input widgets must bind to the loaded config, not the previous one."""
    monkeypatch.setattr(
        "mne_nodes.gui.welcome_tour.ask_user", lambda *args, **kwargs: True
    )
    checklist = main_window.viewer.input_node.input_widget.tab_widget.widget(0)
    selected = checklist.model.index(0, 0).data()
    ct.input_selection_changed([selected], "eeg")
    previous_selection = ct.get("selected_inputs")
    ct.initialize_welcome_tour()
    tour = ct.welcome_tour
    try:
        widget = main_window.viewer.input_node.input_widget
        assert widget.selected_inputs is ct.get("selected_inputs")
        assert widget.selected_inputs is not previous_selection
        for tab_index in range(widget.tab_widget.count() - 1):
            model = widget.tab_widget.widget(tab_index).model
            for row in range(model.rowCount()):
                assert (
                    model.index(row, 0).data(Qt.ItemDataRole.CheckStateRole)
                    == Qt.CheckState.Unchecked
                )
        assert not any(ct.get("selected_inputs").values())
        assert not main_window.viewer.input_node.start_button.isEnabled()
    finally:
        tour.finish()


@pytest.mark.parametrize("cancel", [False, True])
@pytest.mark.parametrize("create_new", [True, False])
def test_welcome_tour_finish_selects_user_pipeline(
    ct, main_window, monkeypatch, tmp_path, qtbot, create_new, cancel
):
    """Finish and Cancel discard the demo and open normal pipeline setup."""
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
        "mne_nodes.gui.welcome_tour.ask_user", lambda *args, **kwargs: True
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
    if cancel:
        tour.show_step(2)
        assert not tour.widget.next_btn.isEnabled()
        qtbot.mouseClick(tour.widget.cancel_btn, Qt.MouseButton.LeftButton)
    else:
        tour.show_step(len(tour.steps) - 1)
        assert tour.widget.next_btn.text() == "Finished"
        qtbot.mouseClick(tour.widget.next_btn, Qt.MouseButton.LeftButton)

    assert prompts == [("Create new", "Use existing")]
    assert "example_function" not in ct.plugins
    assert "example_filter" not in ct.function_meta
    assert ct.config_path == user_config
    assert ct.settings.get("config_path") == user_config
    assert ct.get("parameters") == ({} if create_new else {"x": 2})
    assert not any(ct.get("selected_inputs").values())
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
        "mne_nodes.gui.welcome_tour.ask_user", lambda *args, **kwargs: True
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
        node = viewer.add_function_node("example_filter")
        qtbot.waitUntil(lambda: tour.index == 3)
        assert completed == [2]
        assert tour._target is node
        tour.next_step()
        assert tour.index == 4
        assert not tour.widget.next_btn.isEnabled()

        output = viewer.input_node.output(port_name="eeg")
        input_port = node.input(port_name="raw")
        output.connect_to(input_port)
        qtbot.waitUntil(lambda: tour.index == 5)
        assert completed == [2, 4]
        assert tour.index == 5
        assert tour._target is node.param_box.graphicsProxyWidget()
        assert tour.overlay.highlight_path == tour.compute_highlight_path(tour._target)
        assert not tour.widget.next_btn.isEnabled()
        lowpass = node.parameter_guis["lowpass"].param_widget
        assert lowpass.isEnabled()
        qtbot.keyClick(lowpass, Qt.Key.Key_Up)
        qtbot.waitUntil(lambda: tour.index == 6)
        assert ct.parameter("lowpass", node.name) == 31
        assert tour.index == 6
        assert tour._target is viewer.input_node.input_widget.graphicsProxyWidget()
        assert viewer.input_node.input_widget.isEnabled()
        assert viewer.input_node.input_widget.tab_widget.widget(0).view.isEnabled()
        assert not tour.widget.next_btn.isEnabled()
        ct.input_selection_changed(["sub-01_task-test_eeg.fif"], "eeg")
        qtbot.waitUntil(lambda: tour.index == 7)
        assert completed == [2, 4, 5, 6]
        assert tour._target is viewer.input_node.start_button_proxy
        assert viewer.input_node.start_button.isEnabled()
        assert not node.start_button.isEnabled()
        assert (
            viewer.mapFromScene(node.sceneBoundingRect()).boundingRect().isEmpty()
            is False
        )
    finally:
        tour.finish()


def test_welcome_tour_waits_for_pipeline_start(ct, main_window, monkeypatch, qtbot):
    """The console step is reached only after a process actually starts."""
    monkeypatch.setattr(
        "mne_nodes.gui.welcome_tour.ask_user", lambda *args, **kwargs: True
    )
    main_window.show()
    ct.initialize_welcome_tour()
    tour = ct.welcome_tour
    dock = main_window.console_dock
    starts = []

    def start_pipeline(sequence):
        starts.append(sequence)
        dock.show()

    monkeypatch.setattr(ct, "start", start_pipeline)
    try:
        viewer = main_window.viewer
        node = viewer.add_function_node("example_filter")
        viewer.input_node.output(port_name="eeg").connect_to(
            node.input(port_name="raw")
        )
        ct.input_selection_changed(["sub-01_ses-eeg_task-rest_eeg.eeg"], "eeg")
        tour.show_step(7)
        assert not tour.widget.next_btn.isEnabled()
        tour.next_step()
        assert tour.index == 7
        qtbot.mouseClick(viewer.input_node.start_button, Qt.MouseButton.LeftButton)
        assert len(starts) == 1
        assert dock.isVisible()
        tour.refresh()
        assert tour.index == 7
        assert not tour.widget.next_btn.isEnabled()
        dock.process_started.emit()
        qtbot.waitUntil(lambda: tour.index == 8)
        assert tour._target is dock
        tour.next_step()
        assert tour.index == 9
        assert not tour.overlay.isVisible()
    finally:
        tour.finish()
    # A later process must not call back into the finished/deleted tour.
    dock.process_started.emit()


@pytest.mark.parametrize("on_port", [False, True])
def test_welcome_tour_adds_node_from_context_menu(
    ct, main_window, monkeypatch, qtbot, on_port
):
    """The node-creation step permits choosing functions from real popup menus."""
    monkeypatch.setattr(
        "mne_nodes.gui.welcome_tour.ask_user", lambda *args, **kwargs: True
    )
    ct.initialize_welcome_tour()
    tour = ct.welcome_tour
    viewer = main_window.viewer

    def select_function(menu, position):
        menu.popup(position)
        qtbot.waitUntil(menu.isVisible)
        tour.refresh()
        assert menu.isEnabled()
        actions = [
            action
            for popup in [menu, *menu.findChildren(QMenu)]
            for action in popup.actions()
            if action.text() == "test_filter"
        ]
        assert len(actions) == 1
        action = actions[0]
        popup = action.parent()
        parents = []
        parent = popup.parentWidget()
        while isinstance(parent, QMenu):
            parents.append(parent)
            parent = parent.parentWidget()
        for parent in reversed(parents):
            parent.popup(position)
        assert action.isEnabled()
        popup.popup(position)
        qtbot.waitUntil(popup.isVisible)
        assert popup.isEnabled()
        popup.setActiveAction(action)
        qtbot.mouseClick(
            popup, Qt.MouseButton.LeftButton, pos=popup.actionGeometry(action).center()
        )
        menu.close()

    class TestMenu(QMenu):
        def exec(self, position):
            return select_function(self, position)

    monkeypatch.setattr("mne_nodes.gui.node.node_viewer.QMenu", TestMenu)
    try:
        tour.show_step(2)
        assert not tour.widget.next_btn.isEnabled()
        if on_port:
            port = viewer.input_node.output(port_name="eeg")
            pos = viewer.mapFromScene(port.sceneBoundingRect().center())
        else:
            pos = viewer.viewport().rect().topLeft()
        event = QContextMenuEvent(
            QContextMenuEvent.Reason.Mouse, pos, viewer.viewport().mapToGlobal(pos)
        )
        viewer.contextMenuEvent(event)
        assert len(viewer.function_nodes) == 1
        qtbot.waitUntil(lambda: tour.index == 3)
    finally:
        tour.finish()


@pytest.mark.parametrize("rebuild", [False, True])
@pytest.mark.parametrize("window_input", [False, True])
def test_welcome_tour_input_checkbox_is_clickable(
    ct, main_window, monkeypatch, qtbot, rebuild, window_input
):
    """File selection must work through a real click on the embedded checklist."""
    monkeypatch.setattr(
        "mne_nodes.gui.welcome_tour.ask_user", lambda *args, **kwargs: True
    )
    main_window.show()
    ct.initialize_welcome_tour()
    tour = ct.welcome_tour
    viewer = main_window.viewer
    try:
        assert not viewer.input_node.input_widget.tab_widget.widget(0).view.isEnabled()
        tour.next_step()
        tour.next_step()
        node = viewer.add_function_node("example_filter")
        qtbot.waitUntil(lambda: tour.index == 3)
        tour.next_step()
        viewer.input_node.output(port_name="eeg").connect_to(
            node.input(port_name="raw")
        )
        qtbot.waitUntil(lambda: tour.index == 5)
        input_widget = viewer.input_node.input_widget
        if rebuild:
            input_widget.update_widgets()
        node.parameter_guis["lowpass"].param_widget.setValue(40)
        qtbot.waitUntil(lambda: tour.index == 6)
        assert tour.index == 6
        qtbot.wait(20)
        checklist = input_widget.tab_widget.widget(0)
        list_view = checklist.view
        assert list_view.isEnabled()
        assert list_view.viewport().isEnabled()
        index = checklist.model.index(0, 0)
        assert index.isValid()
        assert index.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Unchecked
        option = QStyleOptionViewItem()
        option.initFrom(list_view)
        option.rect = list_view.visualRect(index)
        list_view.itemDelegate().initStyleOption(option, index)
        checkbox_rect = list_view.style().subElementRect(
            QStyle.SubElement.SE_ItemViewItemCheckIndicator, option, list_view
        )
        proxy = input_widget.graphicsProxyWidget()
        widget_pos = list_view.viewport().mapTo(input_widget, checkbox_rect.center())
        scene_pos = proxy.mapToScene(QPointF(widget_pos))
        viewer.centerOn(scene_pos)
        tour.refresh()
        receiver = main_window.windowHandle() if window_input else viewer.viewport()
        click_pos = viewer.mapFromScene(scene_pos)
        if window_input:
            click_pos = viewer.viewport().mapTo(main_window, click_pos)
        QTest.mousePress(receiver, Qt.MouseButton.LeftButton, pos=click_pos)
        qtbot.wait(150)
        QTest.mouseRelease(receiver, Qt.MouseButton.LeftButton, pos=click_pos)
        assert index.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked
        qtbot.waitUntil(lambda: tour.index == 7)
        assert ct.get("selected_inputs")[input_widget.tab_widget.tabText(0)]
    finally:
        tour.finish()


def test_new_function_node_is_fitted_into_view(ct, main_window):
    """Adding a node outside the current view refits all graph nodes."""
    viewer = main_window.viewer
    node = viewer.add_function_node("test_filter", pos=QPointF(5000, 5000))
    visible_rect = viewer.mapToScene(viewer.viewport().rect()).boundingRect()

    assert visible_rect.contains(node.sceneBoundingRect())


def test_closing_welcome_tour_does_not_save_packaged_pipeline(
    ct, main_window, monkeypatch
):
    """Closing the application during the tour saves only its disposable copy."""
    packaged_config = Path(__file__).parents[1] / "extra" / "Welcome_pipeline.json"
    packaged_bytes = packaged_config.read_bytes()
    previous_config = ct.config_path
    monkeypatch.setattr(
        "mne_nodes.gui.welcome_tour.ask_user", lambda *args, **kwargs: True
    )
    ct.initialize_welcome_tour()
    assert "example_filter" in ct.function_meta
    main_window.viewer.add_function_node("example_filter")
    main_window.viewer.add_function_node("example_filter")
    ct.set("parameters", {"demo": True})
    main_window.close()
    assert packaged_config.read_bytes() == packaged_bytes
    assert ct.settings.get("config_path") == previous_config
    assert not ct.welcome_tour._refresh_timer.isActive()
    assert ct.welcome_tour.demo_directory is None
    assert "example_function" not in ct.plugins
    assert "example_filter" not in ct.function_meta
    assert not main_window.viewer.function_nodes


def test_welcome_plugin_restores_existing_session(ct, main_window):
    """Tour unloading restores collisions without changing device settings."""
    from types import ModuleType

    from mne_nodes.gui.welcome_tour import _load_welcome_plugin

    original = ModuleType("previous_example")
    ct.plugins["example_function"] = original
    metadata = {**ct.get_function_meta("test_filter"), "plugin": "example_function"}
    ct.function_meta["example_filter"] = metadata
    plugin_meta = {"example_function": {"plugin_type": "module"}}
    ct.set("plugin_meta", plugin_meta)
    plugin_settings = ct.settings.get("plugin_config", {}).copy()
    disabled_plugins = ct.settings.get("disabled_plugins", []).copy()
    cleanup = _load_welcome_plugin(ct)
    assert ct.plugins["example_function"] is not original
    assert ct.get_default("lowpass", "example_filter") == 30
    cleanup()
    assert ct.plugins["example_function"] is original
    assert ct.function_meta["example_filter"] is metadata
    assert ct.get("plugin_meta") == {"example_function": {"plugin_type": "module"}}
    assert ct.settings.get("plugin_config", {}) == plugin_settings
    assert ct.settings.get("disabled_plugins", []) == disabled_plugins


def test_welcome_tour_decline_does_not_load_example_plugin(
    ct, main_window, monkeypatch
):
    monkeypatch.setattr(
        "mne_nodes.gui.welcome_tour.ask_user", lambda *args, **kwargs: False
    )
    previous_config = ct.config_path
    ct.initialize_welcome_tour()
    assert ct.config_path == previous_config
    assert "example_function" not in ct.plugins
    assert "example_filter" not in ct.function_meta


def test_welcome_tour_start_failure_unloads_example_plugin(
    ct, main_window, monkeypatch
):
    """Construction failures must not leave the example plugin registered."""
    from mne_nodes.gui.welcome_tour import start_welcome_tour

    monkeypatch.setattr(
        "mne_nodes.gui.welcome_tour.ask_user", lambda *args, **kwargs: True
    )

    def fail_tour(*args, **kwargs):
        raise RuntimeError("Tour construction failed")

    monkeypatch.setattr("mne_nodes.gui.welcome_tour.WelcomeTour", fail_tour)
    previous_plugins = ct.plugins.copy()
    previous_functions = ct.function_meta.copy()
    previous_config = ct.settings.get("config_path")
    with pytest.raises(RuntimeError, match="Tour construction failed"):
        start_welcome_tour(ct, main_window)
    assert ct.plugins == previous_plugins
    assert ct.function_meta == previous_functions
    assert "example_function" not in ct.get("plugin_meta")
    assert ct.settings.get("config_path") == previous_config
    assert not ct.config_path.exists()


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
