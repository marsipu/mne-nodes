"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import json
from pathlib import Path

import pytest
from qtpy.QtCore import QPointF, Qt
from qtpy.QtGui import QContextMenuEvent
from qtpy.QtTest import QTest
from qtpy.QtWidgets import QMenu, QStyle, QStyleOptionViewItem

from mne_nodes.backend.io import type_json_hook
from mne_nodes.gui.main_window import MainWindow
from mne_nodes.gui.welcome_tour import WELCOME_CONFIG_PATH


@pytest.fixture(autouse=True)
def welcome_sample_loader(monkeypatch):
    """Keep GUI tour tests on tiny BIDS data; expose the real loader to its tests."""
    from mne_nodes.gui import welcome_tour

    loader = welcome_tour._ensure_welcome_sample
    monkeypatch.setattr(
        welcome_tour, "_ensure_welcome_sample", lambda *args, **kwargs: None
    )
    return loader


@pytest.fixture
def welcome_tour_enabled(ct):
    """Enable the first-run tour for tests that explicitly start it."""
    ct.settings.set("first_start", True)


def test_main_window_defers_viewer_load_until_controller_ready(settings, qtbot):
    """The main window should not load viewer nodes before the controller setup is finalized."""

    from mne_nodes.backend.controller import Controller
    from mne_nodes.gui.main_window import MainWindow

    controller = Controller(settings=settings)
    settings.set("bids_root", Path(__file__).parent / "tiny_bids")
    main_window = MainWindow(controller)
    qtbot.addWidget(main_window)

    assert main_window.viewer._input_node is None
    assert len(main_window.viewer.nodes) == 0

    main_window.finalize_controller_setup()
    assert main_window.viewer.input_node is not None
    assert main_window.viewer.input_node.scene() is main_window.viewer.scene()
    nodes = dict(main_window.viewer.nodes)
    main_window.finalize_controller_setup()
    assert main_window.viewer.nodes == nodes
    assert all(node.scene() is main_window.viewer.scene() for node in nodes.values())
    main_window.close()


def test_replacing_input_node_removes_previous_dataset(main_window):
    """Replacing the input must remove the old node, scene item and connections."""
    from mne_nodes.gui.node.input_node import InputNode

    viewer = main_window.viewer
    previous_node = viewer.input_node
    previous_id = previous_node.id
    node = viewer.add_input_node()

    assert viewer.input_node is node
    assert previous_id not in viewer.nodes
    assert previous_node not in viewer.scene().items()
    assert [item for item in viewer.nodes.values() if isinstance(item, InputNode)] == [
        node
    ]
    assert [item for item in viewer.scene().items() if isinstance(item, InputNode)] == [
        node
    ]


def test_restart_welcome_tour_action(ct, main_window, monkeypatch):
    """The Help action must start a tour even after the first session."""
    calls = []
    ct.settings.set("first_start", False)
    monkeypatch.setattr(
        ct, "initialize_welcome_tour", lambda **kwargs: calls.append(kwargs)
    )
    help_menu = next(
        menu
        for menu in main_window.menuBar().findChildren(QMenu)
        if menu.title() == "&Help"
    )
    action = next(
        action
        for action in help_menu.actions()
        if action.text() == "&Restart Welcome Tour"
    )
    action.trigger()
    assert calls == [{"force": True}]


def test_restart_welcome_tour_does_not_nest_active_tour(ct, main_window, monkeypatch):
    """Invoking the action during a tour must not replace its plugin snapshot."""
    from types import SimpleNamespace

    tour = SimpleNamespace(_finished=False, finish=lambda **kwargs: None)
    ct.welcome_tour = tour

    def unexpected_start(*args, **kwargs):
        pytest.fail("An active tour must not be started again.")

    monkeypatch.setattr(
        "mne_nodes.gui.welcome_tour.start_welcome_tour", unexpected_start
    )
    main_window.restart_welcome_tour()
    assert ct.welcome_tour is tour


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


@pytest.mark.parametrize("relocate_sample", [False, True])
def test_welcome_tour_initializes_demo_and_tracks_input_node(
    settings, monkeypatch, tmp_path, qtbot, welcome_sample_loader, relocate_sample
):
    """The real tour loads fresh demo state and follows its input node."""
    from mne_bids import BIDSPath

    from tests.conftest import create_test_controller

    monkeypatch.setattr(BIDSPath, "find_empty_room", lambda self: None)
    ct = create_test_controller(settings, tmp_path, monkeypatch)
    main_window = MainWindow(ct)
    qtbot.addWidget(main_window)
    main_window.finalize_controller_setup()
    ct.settings.set("first_start", True)
    checklist = main_window.viewer.input_node.input_widget.tab_widget.widget(0)
    selected = checklist.model.index(0, 0).data()
    ct.input_selection_changed([selected], "eeg")
    previous_selection = ct.get("selected_inputs")
    monkeypatch.setattr(
        "mne_nodes.gui.welcome_tour.ask_user", lambda *args, **kwargs: True
    )
    sample_root = tmp_path / "selected-sample"
    conversions = []
    if relocate_sample:
        from types import SimpleNamespace

        from mne_nodes.gui import welcome_tour

        def write_sample(bids_root):
            conversions.append(bids_root)
            meg_dir = bids_root / "sub-01" / "ses-01" / "meg"
            meg_dir.mkdir(parents=True, exist_ok=True)
            (bids_root / "dataset_description.json").write_text(
                json.dumps({"Name": "sample-dataset"}), encoding="utf-8"
            )
            (meg_dir / "sub-01_ses-01_task-audiovisual_run-1_meg.fif").touch()

        cached_root = tmp_path / "cached-sample"
        write_sample(cached_root)
        conversions.clear()
        sample_root.mkdir()
        ct.settings.set("sample_bids_root", cached_root)
        monkeypatch.setattr(
            welcome_tour, "_ensure_welcome_sample", welcome_sample_loader
        )
        monkeypatch.setattr(welcome_tour, "load_sample_bids", write_sample)
        monkeypatch.setattr(
            welcome_tour,
            "WorkerDialog",
            lambda *args, function, bids_root, **kwargs: SimpleNamespace(
                return_value=function(bids_root=bids_root)
            ),
        )
        monkeypatch.setattr(
            "mne_nodes.backend.controller.ask_user", lambda *args, **kwargs: False
        )

    def select_output_parent(message, input_type, **kwargs):
        assert input_type == "folder", "The tour must not ask for a pipeline name."
        if "bids-root" in message:
            return sample_root
        return tmp_path

    monkeypatch.setattr(
        "mne_nodes.backend.controller.get_user_input", select_output_parent
    )
    ct.initialize_welcome_tour()
    tour = ct.welcome_tour
    try:
        assert ct.settings.get("first_start") is False
        assert set(ct.plugins) == {"example_plugin"}
        assert "example_filter" in ct.function_meta
        assert tour.steps[0]["widget"] is main_window.viewer
        ct.ensure_ready()
        assert ct.name == "Welcome"
        assert ct.deriv_root == tmp_path / "Welcome_derivatives"
        assert ct.plot_path == tmp_path / "Welcome_plots"
        if relocate_sample:
            assert conversions == [sample_root]
            assert ct.bids_root == sample_root
            assert ct.settings.get("sample_bids_root") == sample_root
            assert ct.get_dataset_name() == "sample-dataset"
            tabs = main_window.viewer.input_node.input_widget.tab_widget
            assert "meg" in [tabs.tabText(index) for index in range(tabs.count())]
        main_window.finalize_controller_setup()
        node = main_window.viewer.input_node
        assert node.scene() is main_window.viewer.scene()
        widget = node.input_widget
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
        assert not node.start_button.isEnabled()
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
        tour.finish(notify=False)


def test_input_widget_refresh_uses_current_selection(ct, main_window):
    """Refreshing an existing widget must not reuse a previous pipeline's selection."""
    widget = main_window.viewer.input_node.input_widget
    filename = widget.tab_widget.widget(0).model.index(0, 0).data()
    ct.input_selection_changed([filename], "eeg")
    previous_selection = widget.selected_inputs
    ct.set("selected_inputs", {"eeg": [], "subject": []})

    widget.update_widgets()

    assert widget.selected_inputs is ct.get("selected_inputs")
    assert widget.selected_inputs is not previous_selection
    assert (
        widget.tab_widget.widget(0)
        .model.index(0, 0)
        .data(Qt.ItemDataRole.CheckStateRole)
        == Qt.CheckState.Unchecked
    )
    assert not main_window.viewer.input_node.start_button.isEnabled()


@pytest.mark.parametrize("tour", [False, True])
def test_bids_root_switch_replaces_input_dataset_information(
    ct, main_window, monkeypatch, tmp_path, welcome_sample_loader, tour
):
    """An existing input node must display only the newly selected root's data."""
    node = main_window.viewer.input_node
    widget = node.input_widget
    old_filename = widget.tab_widget.widget(0).model.index(0, 0).data()
    ct.input_selection_changed([old_filename], "eeg")
    ct.set("custom_groups", {"previous-group": [old_filename]})
    ct.set("group_by", "custom")
    widget.update_widgets()
    ct.settings.set("deriv_root", tmp_path / "previous-derivatives")
    ct.settings.set("plot_root", tmp_path / "previous-plots")

    root = tmp_path / "new-bids"
    meg_dir = root / "sub-01" / "ses-01" / "meg"
    meg_dir.mkdir(parents=True)
    filename = "sub-01_ses-01_task-audiovisual_run-1_meg.fif"
    (meg_dir / filename).touch()
    (root / "dataset_description.json").write_text(
        json.dumps({"Name": "sample-dataset"}), encoding="utf-8"
    )
    if tour:
        ct.settings.set("sample_bids_root", root)
        welcome_sample_loader(ct, main_window)
    else:
        monkeypatch.setattr(
            "mne_nodes.backend.controller.ask_user", lambda *args, **kwargs: True
        )
        ct.bids_root = root

    assert main_window.viewer.input_node is node
    assert node.input_widget is widget
    assert node.name == "sample-dataset"
    assert ct.get("bids_dataset_name") == "sample-dataset"
    assert [widget.tab_widget.tabText(index) for index in range(2)] == ["meg", "Groups"]
    assert widget.tab_widget.count() == 2
    model = widget.tab_widget.widget(0).model
    assert model.rowCount() == 1
    assert model.index(0, 0).data() == filename
    assert (
        model.index(0, 0).data(Qt.ItemDataRole.CheckStateRole)
        == Qt.CheckState.Unchecked
    )
    assert widget.group_tree.model.rowCount() == 0
    assert ct.get("custom_groups") == {}
    assert not any(ct.get("selected_inputs").values())
    assert ct.settings.get("deriv_root") is None
    assert ct.settings.get("plot_root") is None
    assert not node.start_button.isEnabled()


@pytest.mark.parametrize("cancel", [False, True])
@pytest.mark.parametrize("create_new", [True, False])
def test_welcome_tour_finish_selects_user_pipeline(
    ct,
    main_window,
    monkeypatch,
    tmp_path,
    qtbot,
    welcome_tour_enabled,
    create_new,
    cancel,
):
    """Finish and Cancel discard the demo and open normal pipeline setup."""
    from mne_nodes.backend.controller import default_config

    packaged_config = WELCOME_CONFIG_PATH
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

    monkeypatch.setattr("mne_nodes.backend.controller.ask_user_custom", choose_pipeline)
    monkeypatch.setattr(
        ct, "_prompt_pipeline_path", lambda message: ("new", user_config)
    )

    def select_path(*args, **kwargs):
        input_type = kwargs.get("input_type")
        if input_type is None and len(args) > 1:
            input_type = args[1]
        if input_type == "folder":
            return tmp_path
        return user_config

    monkeypatch.setattr("mne_nodes.backend.controller.get_user_input", select_path)
    if cancel:
        tour.show_step(2)
        assert not tour.widget.next_btn.isEnabled()
        qtbot.mouseClick(tour.widget.cancel_btn, Qt.MouseButton.LeftButton)
    else:
        tour.show_step(len(tour.steps) - 1)
        assert tour.widget.next_btn.text() == "Finished"
        qtbot.mouseClick(tour.widget.next_btn, Qt.MouseButton.LeftButton)

    assert prompts == [("Create new", "Use existing")]
    assert "example_plugin" not in ct.plugins
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
    ct, main_window, monkeypatch, qtbot, welcome_tour_enabled
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


def test_welcome_tour_waits_for_pipeline_start(
    ct, main_window, monkeypatch, qtbot, welcome_tour_enabled
):
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
        assert tour.overlay.isVisible()
        tour.show_step(len(tour.steps) - 1)
        assert not tour.overlay.isVisible()
    finally:
        tour.finish()
    # A later process must not call back into the finished/deleted tour.
    dock.process_started.emit()


@pytest.mark.parametrize("on_port", [False, True])
def test_welcome_tour_adds_node_from_context_menu(
    ct, main_window, monkeypatch, qtbot, welcome_tour_enabled, on_port
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
            if action.text() == "example_filter"
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
    ct, main_window, monkeypatch, qtbot, welcome_tour_enabled, rebuild, window_input
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
    ct, main_window, monkeypatch, welcome_tour_enabled
):
    """Closing the application during the tour saves only its disposable copy."""
    packaged_config = WELCOME_CONFIG_PATH
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
    assert "example_plugin" not in ct.plugins
    assert "example_filter" not in ct.function_meta
    assert not main_window.viewer.function_nodes


def test_welcome_plugin_restores_existing_session(ct, main_window):
    """Tour unloading restores collisions without changing device settings."""
    from types import ModuleType

    from mne_nodes.gui.welcome_tour import _load_welcome_plugin

    original = ModuleType("previous_example")
    ct.plugins["example_plugin"] = original
    metadata = {**ct.get_function_meta("test_filter"), "plugin": "example_plugin"}
    ct.function_meta["example_filter"] = metadata
    plugin_meta = {"example_plugin": {"plugin_type": "module"}}
    ct.set("plugin_meta", plugin_meta)
    plugin_settings = ct.settings.get("plugin_config", {}).copy()
    disabled_plugins = ct.settings.get("disabled_plugins", []).copy()
    cleanup = _load_welcome_plugin(ct)
    assert set(ct.plugins) == {"example_plugin"}
    assert set(ct.function_meta) == {"example_filter"}
    assert ct.get_default("lowpass", "example_filter") == 30
    cleanup()
    assert ct.plugins["example_plugin"] is original
    assert ct.function_meta["example_filter"] is metadata
    assert ct.get("plugin_meta") == {"example_plugin": {"plugin_type": "module"}}
    assert ct.settings.get("plugin_config", {}) == plugin_settings
    assert ct.settings.get("disabled_plugins", []) == disabled_plugins


def test_welcome_tour_decline_does_not_load_example_plugin(
    ct, main_window, monkeypatch, welcome_tour_enabled
):
    monkeypatch.setattr(
        "mne_nodes.gui.welcome_tour.ask_user", lambda *args, **kwargs: False
    )
    previous_config = ct.config_path
    previous_bids_root = ct.bids_root
    ct.initialize_welcome_tour()
    assert ct.config_path == previous_config
    assert ct.bids_root == previous_bids_root
    assert "example_plugin" not in ct.plugins
    assert "example_filter" not in ct.function_meta


@pytest.mark.parametrize("available", ["current", "cached", "missing", "incomplete"])
def test_welcome_sample_reuses_or_loads_data(
    ct, monkeypatch, tmp_path, welcome_sample_loader, available
):
    """Only a complete converted dataset should skip the sample-data worker."""
    from types import SimpleNamespace

    from mne_nodes.gui import welcome_tour

    sample_root = tmp_path / "sample-bids"
    ct.settings.set("sample_bids_root", sample_root)
    ct.settings.set("deriv_root", tmp_path / "old-derivatives")
    ct.settings.set("plot_root", tmp_path / "old-plots")
    ct.set("selected_inputs", {"eeg": ["old_file.vhdr"], "subject": ["old"]})
    ct.set("custom_groups", {"old-group": ["old_file.vhdr"]})
    calls = []

    def write_sample(bids_root):
        meg_dir = bids_root / "sub-01" / "ses-01" / "meg"
        meg_dir.mkdir(parents=True, exist_ok=True)
        (bids_root / "dataset_description.json").write_text(
            json.dumps({"Name": "sample-dataset"}), encoding="utf-8"
        )
        (meg_dir / "sub-01_ses-01_task-audiovisual_run-1_meg.fif").touch()

    if available in ("current", "cached"):
        write_sample(sample_root)
    elif available == "incomplete":
        sample_root.mkdir()
        (sample_root / "dataset_description.json").write_text(
            json.dumps({"Name": "sample-dataset"}), encoding="utf-8"
        )
    if available == "current":
        ct.settings.set("bids_root", sample_root)

    def run_worker(parent, *, function, bids_root, **kwargs):
        calls.append((parent, bids_root, kwargs))
        return SimpleNamespace(return_value=function(bids_root=bids_root))

    monkeypatch.setattr(welcome_tour, "load_sample_bids", write_sample)
    monkeypatch.setattr(welcome_tour, "WorkerDialog", run_worker)
    parent = object()
    welcome_sample_loader(ct, parent)
    assert ct.bids_root == sample_root
    assert ct.settings.get("sample_bids_root") == sample_root
    if available != "current":
        assert not any(ct.get("selected_inputs").values())
        assert ct.get("custom_groups") == {}
        assert ct.settings.get("deriv_root") is None
        assert ct.settings.get("plot_root") is None
        assert ct.get("bids_dataset_name") == "sample-dataset"
    assert len(calls) == (1 if available in ("missing", "incomplete") else 0)
    if calls:
        assert calls[0][0] is parent
        assert calls[0][2]["blocking"] is True
        assert calls[0][2]["return_exception"] is True


@pytest.mark.parametrize("worker_error", [False, True])
def test_welcome_sample_failure_preserves_dataset(
    ct, monkeypatch, tmp_path, welcome_sample_loader, worker_error
):
    """Worker errors and incomplete conversion must not select a broken dataset."""
    from types import SimpleNamespace

    from mne_nodes.backend.exception_handling import ExceptionTuple
    from mne_nodes.gui import welcome_tour

    previous_root = ct.bids_root
    ct.settings.set("sample_bids_root", tmp_path / "missing-sample")
    error = RuntimeError("Sample conversion failed")
    result = ExceptionTuple(RuntimeError, error, "traceback") if worker_error else None
    monkeypatch.setattr(
        welcome_tour,
        "WorkerDialog",
        lambda *args, **kwargs: SimpleNamespace(return_value=result),
    )
    with pytest.raises(RuntimeError):
        welcome_sample_loader(ct, None)
    assert ct.bids_root == previous_root


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
    assert "example_plugin" not in ct.get("plugin_meta")
    assert ct.settings.get("config_path") == previous_config
    assert not ct.config_path.exists()


def test_window_registry_lookup_and_replacement(settings, qtbot):
    """Closing an older window must not unregister its replacement."""
    from mne_nodes.backend.controller import Controller
    from mne_nodes.gui.widget_registry import get_widget

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
