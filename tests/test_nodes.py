"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

from copy import deepcopy
from pprint import pprint

import pytest
from qtpy.QtCore import QObject, QPoint, QPointF, Qt
from qtpy.QtWidgets import QLabel

from mne_nodes.gui.gui_utils import mouseDrag, mouseMove, mousePress, mouseRelease
from mne_nodes.gui.node.node_defaults import defaults
from mne_nodes.gui.node.ports import Port
from tests.conftest import _add_complex_nodes


def test_input_metadata_outputs_are_not_selectable(nodeviewer):
    """BIDS metadata has connectable ports but no independent selection tabs."""
    node = nodeviewer.input_node
    assert node is not None
    tabs = {
        node.input_widget.tab_widget.tabText(index)
        for index in range(node.input_widget.tab_widget.count())
    }
    for data_type in ("event_id", "info", "trans", "subject"):
        assert node.output(port_name=data_type).accepted_ports == [data_type]
        assert data_type not in tabs
        if data_type != "subject":
            assert data_type not in node.ct.get("selected_inputs")
    assert "eeg" in tabs
    assert "Groups" in tabs


def test_recording_and_anatomy_outputs_require_selection(nodeviewer):
    """A datatype being present in the dataset does not enable its output."""
    from mne_bids import get_bids_path_from_fname

    ct = nodeviewer.ct
    node = nodeviewer.input_node
    eeg = get_bids_path_from_fname(next(ct.bids_root.rglob("*_eeg.vhdr")))
    meg = eeg.copy().update(datatype="meg", suffix="meg", extension=".fif")
    meg.directory.mkdir(parents=True, exist_ok=True)
    meg.fpath.touch()
    anat = eeg.copy().update(
        datatype="anat", task=None, suffix="T1w", extension=".nii.gz"
    )
    anat.directory.mkdir(parents=True, exist_ok=True)
    anat.fpath.touch()
    node.update_widgets()
    ct.set("selected_inputs", {})
    ct.refresh_input_outputs()
    for datatype in ("eeg", "meg", "anat", "info", "event_id", "trans", "subject"):
        port = node.output(port_name=datatype)
        assert not port.isEnabled()
        assert port.toolTip()

    ct.input_selection_changed([eeg.basename], "eeg")
    assert node.output(port_name="eeg").isEnabled()
    assert not node.output(port_name="meg").isEnabled()
    assert not node.output(port_name="anat").isEnabled()
    ct.input_selection_changed([anat.basename], "anat")
    assert node.output(port_name="anat").isEnabled()
    assert not node.output(port_name="meg").isEnabled()
    ct.input_selection_changed([meg.basename], "meg")
    assert node.output(port_name="meg").isEnabled()
    ct.input_selection_changed([], "eeg")
    assert not node.output(port_name="eeg").isEnabled()
    assert node.output(port_name="meg").isEnabled()
    ct.input_selection_changed([], "meg")
    assert not node.output(port_name="meg").isEnabled()
    assert node.output(port_name="anat").isEnabled()
    assert not node.output(port_name="info").isEnabled()
    anat.fpath.unlink()
    ct.refresh_input_outputs()
    assert not node.output(port_name="anat").isEnabled()
    assert "missing" in node.output(port_name="anat").toolTip()


def test_input_output_availability_tracks_all_selected_recordings(nodeviewer):
    """Mixed selections disable MRI outputs without destroying graph connections."""
    import mne
    from mne_bids import get_bids_path_from_fname

    from mne_nodes.backend.coregistration import trans_path

    ct = nodeviewer.ct
    node = nodeviewer.input_node
    first = get_bids_path_from_fname(next(ct.bids_root.rglob("*_eeg.vhdr")))
    second = first.copy().update(task="other", run="99")
    second.fpath.touch()
    subject = f"sub-{first.subject}"
    for folder in ("mri", "surf", "label"):
        (ct.ensure_subjects_dir(False) / subject / folder).mkdir(parents=True)
    root = ct.ensure_deriv_root(False)
    destination = trans_path(first, root)
    destination.parent.mkdir(parents=True)
    mne.write_trans(destination, mne.transforms.Transform("head", "mri"))
    eeg = node.output(port_name="eeg")
    connected = list(eeg.connected_ports)
    trans = node.output(port_name="trans")
    mri = node.output(port_name="subject")

    ct.input_selection_changed([first.basename], "eeg")
    assert trans.isEnabled()
    assert mri.isEnabled()
    assert node.output(port_name="info").isEnabled()
    assert node.output(port_name="event_id").isEnabled()

    ct.input_selection_changed([first.basename, second.basename], "eeg")
    assert not trans.isEnabled()
    assert second.basename in trans.toolTip()
    assert mri.isEnabled()
    destination = trans_path(second, root)
    mne.write_trans(destination, mne.transforms.Transform("head", "mri"))
    ct.refresh_input_outputs()
    assert trans.isEnabled()
    ct.set("coreg_subjects", {second.basename: "absent-mri"})
    ct.refresh_input_outputs()
    assert not mri.isEnabled()
    assert "FreeSurfer" in mri.toolTip()
    assert node.output(port_name="eeg") is eeg
    assert eeg.connected_ports == connected
    node.update_widgets()
    assert node.output(port_name="eeg") is eeg
    assert eeg.connected_ports == connected

    ct.input_selection_changed([], "eeg")
    assert not trans.isEnabled()
    assert not mri.isEnabled()
    assert not node.output(port_name="info").isEnabled()


def test_checking_recording_does_not_rescan_dataset(
    nodeviewer, monkeypatch, record_property
):
    """Checkbox changes reuse dataset inventory, but explicit refresh rescans it."""
    from time import perf_counter
    from unittest.mock import Mock

    from mne_nodes.gui.widgets.list_widgets import CheckListProgress

    ct = nodeviewer.ct
    node = nodeviewer.input_node
    tabs = node.input_widget.tab_widget
    widget = next(
        tabs.widget(index)
        for index in range(tabs.count())
        if tabs.tabText(index) == "eeg"
    )
    assert isinstance(widget, CheckListProgress)
    index = widget.model.index(0, 0)
    widget.model.setData(index, Qt.CheckState.Unchecked, Qt.ItemDataRole.CheckStateRole)
    candidates = Mock(wraps=ct._get_datatype_candidates)
    datatypes = Mock(wraps=ct.get_datatypes)
    items = Mock(wraps=ct.get_datatype_items)
    monkeypatch.setattr(ct, "_get_datatype_candidates", candidates)
    monkeypatch.setattr(ct, "get_datatypes", datatypes)
    monkeypatch.setattr(ct, "get_datatype_items", items)
    start = perf_counter()
    for _ in range(20):
        widget.model.setData(
            index, Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole
        )
        assert node.output(port_name="eeg").isEnabled()
        widget.model.setData(
            index, Qt.CheckState.Unchecked, Qt.ItemDataRole.CheckStateRole
        )
        assert not node.output(port_name="eeg").isEnabled()
    elapsed = perf_counter() - start
    record_property("forty_checkbox_changes_seconds", elapsed)
    assert elapsed < 1.0
    candidates.assert_not_called()
    datatypes.assert_not_called()
    assert all(call.args == ("subject",) for call in items.call_args_list)
    items.reset_mock()
    ct.refresh_input_outputs()
    assert [call.args for call in items.call_args_list].count(("emptyroom",)) == 1


def test_unavailable_auxiliary_checks_short_circuit(nodeviewer, monkeypatch):
    """A missing association disables its output without repeating failing scans."""
    from unittest.mock import Mock

    from mne_bids import get_bids_path_from_fname

    ct = nodeviewer.ct
    first = get_bids_path_from_fname(ct.get_datatype_items("eeg")[0]).update(
        root=ct.bids_root
    )
    second = first.copy().update(run="99")
    second.fpath.touch()
    ct.ensure_deriv_root(False)
    missing_trans = Mock(return_value=None)
    monkeypatch.setattr("mne_nodes.backend.controller.find_trans", missing_trans)
    ct.set("selected_inputs", {"eeg": [first.basename, second.basename]})
    ct.input_output_availability()
    missing_trans.assert_called_once()


def test_subject_output_uses_recordings_without_segmentation_tab(nodeviewer):
    """MRI reconstructions are resolved from files and genuine recording groups."""
    from mne_bids import get_bids_path_from_fname

    ct = nodeviewer.ct
    node = nodeviewer.input_node
    recording = get_bids_path_from_fname(next(ct.bids_root.rglob("*_eeg.vhdr")))
    subject = f"sub-{recording.subject}"
    for folder in ("mri", "surf", "label"):
        (ct.ensure_subjects_dir(False) / subject / folder).mkdir(parents=True)
    node.update_widgets()
    tabs = node.input_widget.tab_widget
    assert "subject" not in {tabs.tabText(index) for index in range(tabs.count())}
    output = node.output(port_name="subject")
    for grouped, enabled in ((False, False), (False, True), (True, True)):
        ct.set("selected_inputs", {})
        if enabled:
            if grouped:
                ct.input_selection_changed([recording.subject], "subject")
            else:
                ct.input_selection_changed([recording.basename], "eeg")
        else:
            ct.refresh_input_outputs()
        assert output.isEnabled() is enabled
        assert ct.selected_recordings() == ([recording] if enabled else [])


def test_unavailable_input_connections_survive_save_load(nodeviewer):
    """A missing transformation blocks UI connections but preserves saved wiring."""
    ct = nodeviewer.ct
    node = nodeviewer.input_node
    function = nodeviewer.node(node_name="test_filter")
    ct.function_meta["test_filter"]["inputs"]["trans"] = {
        "accepted_ports": ["trans"],
        "optional": False,
    }
    target = function.add_input("trans", accepted_ports=["trans"])
    trans = node.output(port_name="trans")
    # Restore-style connections remain possible without allowing interactive drags.
    trans.connect_to(target)
    assert trans.connected(target)
    assert not nodeviewer._ports_can_connect(trans, target)
    config = nodeviewer.to_dict()
    nodeviewer.load_nodes(config)
    trans = nodeviewer.input_node.output(port_name="trans")
    assert not trans.isEnabled()
    assert len(trans.connected_ports) == 1


def test_disabled_output_cannot_create_connections_from_context_menu(
    nodeviewer, monkeypatch
):
    """The context menu must not bypass selection-dependent output availability."""
    from unittest.mock import Mock

    trans = nodeviewer.input_node.output(port_name="trans")
    attention = Mock()
    monkeypatch.setattr(
        "mne_nodes.gui.node.node_viewer.raise_user_attention", attention
    )
    event = Mock()
    nodeviewer._show_port_context_menu(trans, event)
    attention.assert_called_once_with(trans.toolTip(), message_type="info")
    event.accept.assert_called_once_with()


@pytest.mark.parametrize("accept", [False, True])
def test_input_directory_buttons(ct, qtbot, tmp_path, monkeypatch, accept):
    from mne_nodes.gui.node.input_node import InputWidget

    old_directory = ct.bids_root
    new_directory = tmp_path / "new_input"
    new_directory.mkdir()
    selections = {"eeg": ["old_file.vhdr"]}
    ct.set("selected_inputs", selections.copy())
    monkeypatch.setattr(
        ct, "get_all_datatype_items", lambda: {"eeg": ["old_file.vhdr"]}
    )
    monkeypatch.setattr(ct, "get_group_by_strings", lambda group_by: {})
    widget = InputWidget(ct)
    qtbot.addWidget(widget)
    confirmations = []
    monkeypatch.setattr(
        "mne_nodes.backend.controller.ask_user",
        lambda message: confirmations.append(message) or accept,
    )
    monkeypatch.setattr(
        "mne_nodes.gui.node.input_node.get_user_input",
        lambda *args, **kwargs: new_directory,
    )

    assert not hasattr(widget, "subdir_bt")
    qtbot.mouseClick(widget.root_bt, Qt.MouseButton.LeftButton)

    assert len(confirmations) == 1
    assert ct.bids_root == (new_directory if accept else old_directory)
    for index in range(1):
        data_type = widget.tab_widget.tabText(index)
        expected = selections[data_type]
        if accept:
            expected = []
        assert widget.tab_widget.widget(index).model._checked == expected
        assert ct.get("selected_inputs")[data_type] == expected


def test_nodes_basic_interaction(nodeviewer):
    ct = nodeviewer.ct
    ct.input_selection_changed(ct.get_datatype_items("eeg")[:1], "eeg")
    node1 = nodeviewer.input_node
    node2 = nodeviewer.node(node_name="test_filter")
    port1 = node1.output(port_idx=0)
    port2 = node2.input(port_name="raw")
    assert port1.connected(port2)
    port1.disconnect_from(port2)
    assert not port1.connected(port2)
    # Create connection by mouse
    out1_pos = nodeviewer.port_position_view(port_type="out", port_idx=0, node_idx=0)
    in2_pos = nodeviewer.port_position_view(port_type="in", port_idx=0, node_idx=1)
    mouseDrag(
        widget=nodeviewer.viewport(),
        positions=[out1_pos, in2_pos],
        button=Qt.MouseButton.LeftButton,
    )
    # Check if new connection was created
    assert port1.connected(port2)
    # Slice both connections
    start_slice_pos = QPointF(out1_pos.x() + 20, out1_pos.y() - 20)
    end_slice_pos = QPointF(in2_pos.x() - 20, in2_pos.y() + 20)
    mouseDrag(
        widget=nodeviewer.viewport(),
        positions=[start_slice_pos, end_slice_pos],
        button=Qt.MouseButton.LeftButton,
        modifier=Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    # Check if connection was sliced
    assert not port1.connected(port2)
    # Connect again and check if connection is visible
    mouseDrag(
        widget=nodeviewer.viewport(),
        positions=[out1_pos, in2_pos],
        button=Qt.MouseButton.LeftButton,
    )
    assert port1.connected(port2)

    # Reverse drag direction should also create the connection reliably,
    # including a slightly imprecise drop near the target port.
    port1.disconnect_from(port2)
    assert not port1.connected(port2)
    # Keep the imprecise drop inside the port's hit area.
    near_out1_pos = QPointF(out1_pos.x() + 2, out1_pos.y() + 2)
    mouseDrag(
        widget=nodeviewer.viewport(),
        positions=[in2_pos, near_out1_pos],
        button=Qt.MouseButton.LeftButton,
    )
    assert port1.connected(port2)


def test_nodes_click_to_click_connection(nodeviewer, qtbot):
    ct = nodeviewer.ct
    ct.input_selection_changed(ct.get_datatype_items("eeg")[:1], "eeg")
    node1 = nodeviewer.input_node
    node2 = nodeviewer.node(node_name="test_filter")
    out_port = node1.output(port_idx=0)
    in_port = node2.input(port_name="raw")

    # Start from a disconnected state.
    if out_port.connected(in_port):
        out_port.disconnect_from(in_port)
    assert not out_port.connected(in_port)

    out_pos = nodeviewer.port_position_view(port_type="out", port_idx=0, node_idx=0)
    in_pos = nodeviewer.port_position_view(port_type="in", port_idx=0, node_idx=1)

    # Click source port, then click target port (no drag).
    qtbot.mouseClick(
        nodeviewer.viewport(), Qt.MouseButton.LeftButton, pos=out_pos.toPoint()
    )
    qtbot.mouseClick(
        nodeviewer.viewport(), Qt.MouseButton.LeftButton, pos=in_pos.toPoint()
    )

    assert out_port.connected(in_port)


def test_port_highlight_api(nodeviewer):
    port = nodeviewer.input_node.output(port_name="eeg")

    port.set_connection_highlight(True)
    assert port.connection_highlight is True
    assert defaults["ports"]["highlight_scale"] > 1.0

    port.set_connection_highlight(False)
    assert port.connection_highlight is False

    port.set_connection_highlight()
    assert port.connection_highlight is None


def test_port_highlight_during_mouse_drag(nodeviewer):
    ct = nodeviewer.ct
    ct.input_selection_changed(ct.get_datatype_items("eeg")[:1], "eeg")
    input_node = nodeviewer.input_node
    filter_node = nodeviewer.node(node_name="test_filter")
    evokeds_node = nodeviewer.add_function_node("test_evokeds")

    start_port = input_node.output(port_name="eeg")
    compatible_port = filter_node.input(port_name="raw")
    incompatible_port = evokeds_node.input(port_name="epochs")
    same_type_port = filter_node.output(port_name="raw")

    start_port.disconnect_from(compatible_port)

    start_pos = nodeviewer.port_position_view(
        node_id=input_node.id, port_id=start_port.id
    )
    drag_pos = QPointF(start_pos.x() + 40, start_pos.y() + 40)

    # Press on the port and drag into empty space to start a live connection.
    mousePress(
        widget=nodeviewer.viewport(), pos=start_pos, button=Qt.MouseButton.LeftButton
    )
    mouseMove(
        widget=nodeviewer.viewport(), pos=drag_pos, button=Qt.MouseButton.LeftButton
    )

    assert compatible_port.connection_highlight is True
    assert incompatible_port.connection_highlight is False
    assert same_type_port.connection_highlight is False
    assert start_port.connection_highlight is None

    # Releasing in empty space ends the live connection and clears highlights.
    mouseRelease(
        widget=nodeviewer.viewport(), pos=drag_pos, button=Qt.MouseButton.LeftButton
    )

    for node in (input_node, filter_node, evokeds_node):
        for port in node.ports:
            assert port.connection_highlight is None
    assert not start_port.connected(compatible_port)


def test_right_click_opens_context_menu(nodeviewer, monkeypatch):
    calls = []

    class FakeMenu(QObject):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.parent = parent

        def addMenu(self, _title):
            return self

        def addAction(self, action):
            return action

        def addSeparator(self):
            return None

        def exec(self, *args, **kwargs):
            calls.append(True)

        def isEmpty(self):
            return False

    monkeypatch.setattr("mne_nodes.gui.node.node_viewer.QMenu", FakeMenu)

    class FakeContextMenuEvent:
        def __init__(self, pos):
            self._pos = pos
            self.accepted = False

        def pos(self):
            return self._pos

        def globalPos(self):
            return self._pos

        def accept(self):
            self.accepted = True

    click_pos = nodeviewer.viewport().rect().center()
    nodeviewer.contextMenuEvent(FakeContextMenuEvent(click_pos))

    assert calls


def test_right_drag_does_not_open_context_menu(nodeviewer, monkeypatch):
    calls = []

    class FakeMenu(QObject):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.parent = parent

        def addMenu(self, _title):
            return self

        def addAction(self, action):
            return action

        def addSeparator(self):
            return None

        def exec(self, *args, **kwargs):
            calls.append(True)

        def isEmpty(self):
            return False

    monkeypatch.setattr("mne_nodes.gui.node.node_viewer.QMenu", FakeMenu)

    start_pos = nodeviewer.viewport().rect().center()
    end_pos = start_pos + QPoint(60, 0)
    mouseDrag(
        widget=nodeviewer.viewport(),
        positions=[start_pos, end_pos],
        button=Qt.MouseButton.RightButton,
    )

    assert not calls


def test_right_click_port_opens_port_context_menu(nodeviewer, monkeypatch):
    ct = nodeviewer.ct
    ct.input_selection_changed(ct.get_datatype_items("eeg")[:1], "eeg")
    calls = []
    action_texts = []

    class FakeMenu(QObject):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.parent = parent
            self.actions = []

        def addMenu(self, _title):
            return self

        def addAction(self, action):
            self.actions.append(action)
            return action

        def addSeparator(self):
            return None

        def exec(self, *args, **kwargs):
            calls.append(True)
            action_texts.extend(
                [action.text() for action in self.actions if hasattr(action, "text")]
            )

        def isEmpty(self):
            return False

    monkeypatch.setattr("mne_nodes.gui.node.node_viewer.QMenu", FakeMenu)

    class FakeContextMenuEvent:
        def __init__(self, pos):
            self._pos = pos
            self.accepted = False

        def pos(self):
            return self._pos

        def globalPos(self):
            return self._pos

        def accept(self):
            self.accepted = True

    click_pos = nodeviewer.port_position_view(
        port_type="out", port_idx=0, node_idx=0
    ).toPoint()
    nodeviewer.contextMenuEvent(FakeContextMenuEvent(click_pos))

    assert calls
    assert "test_epochs" in action_texts


def test_node_serialization(nodeviewer):
    """Test serialization and deserialization of NodeViewer."""
    viewer_dict = nodeviewer.to_dict()
    nodeviewer.clear()
    nodeviewer.from_dict(viewer_dict)
    second_viewer_dict = nodeviewer.to_dict()

    input_node = nodeviewer.input_node
    function_node = nodeviewer.node(node_name="test_filter")

    assert len(viewer_dict["nodes"]) == len(second_viewer_dict["nodes"])
    assert input_node is not None
    assert function_node is not None
    assert input_node.output(port_name="eeg").connected(
        function_node.input(port_name="raw")
    )
    assert len(
        [item for item in input_node.childItems() if isinstance(item, Port)]
    ) == len(input_node.ports)


def test_show_nodeviewer(nodeviewer):
    """Test if NodeViewer can be shown."""
    nodeviewer.show()
    assert nodeviewer.isVisible()

    # Check if the viewport is correctly set
    assert nodeviewer.viewport() is not None

    # Check if the nodes are correctly laid out
    assert len(nodeviewer.nodes) > 0
    for node in nodeviewer.nodes.values():
        assert node.isVisible()


def test_exec_order(qtbot, ct):
    from mne_nodes.gui.node.node_viewer import NodeViewer

    viewer = NodeViewer(ct)
    qtbot.addWidget(viewer)
    _add_complex_nodes(viewer)

    n = viewer.node(node_idx=0)
    eo = viewer.get_node_sequence(n)
    pprint("first node:")
    pprint(eo)

    n = viewer.node(node_name="test_filter")
    eo = viewer.get_node_sequence(n)
    pprint("test_filter:")
    pprint(eo)

    n = viewer.node(node_name="test_epochs")
    eo = viewer.get_node_sequence(n)
    pprint("epoch_raw:")
    pprint(eo)

    viewer.show()


def test_exec_order_diamond(qtbot, ct):
    """Multi-input nodes must run after all of their upstream chains."""
    from mne_nodes.gui.node.node_viewer import NodeViewer

    viewer = NodeViewer(ct)
    qtbot.addWidget(viewer)
    combine_meta = deepcopy(ct.get_function_meta("test_evokeds"))
    combine_meta["inputs"]["raw"] = deepcopy(
        ct.get_function_meta("test_filter")["inputs"]["raw"]
    )
    combine_meta["outputs"] = {}
    ct.function_meta["test_combine"] = combine_meta
    in_node = viewer.add_input_node()
    combine_node = viewer.add_function_node("test_combine")
    filter_node = viewer.add_function_node("test_filter")
    epochs_node = viewer.add_function_node("test_epochs")
    evokeds_node = viewer.add_function_node("test_evokeds")
    # The short path to test_combine is connected (and thus discovered) first
    in_port = in_node.output(port_idx=0)
    in_port.connect_to(combine_node.input(port_name="raw"))
    in_port.connect_to(filter_node.input(port_name="raw"))
    filter_node.output(port_name="raw").connect_to(epochs_node.input(port_name="raw"))
    epochs_out = epochs_node.output(port_name="epochs")
    epochs_out.connect_to(combine_node.input(port_name="epochs"))
    epochs_out.connect_to(evokeds_node.input(port_name="epochs"))
    assert epochs_out.connected(combine_node.input(port_name="epochs"))

    def names(start):
        return [d["name"] for d in viewer.get_node_sequence(start)["file"]]

    order = names(in_node)
    assert sorted(order) == sorted(
        ["test_combine", "test_filter", "test_epochs", "test_evokeds"]
    )
    assert order.index("test_filter") < order.index("test_epochs")
    assert order.index("test_epochs") < order.index("test_combine")
    assert order.index("test_epochs") < order.index("test_evokeds")

    # Starting from an intermediate node includes the missing upstream chains
    # of downstream nodes, but not the upstream nodes of the start node.
    assert names(epochs_node) == ["test_epochs", "test_combine", "test_evokeds"]
    assert names(combine_node) == ["test_combine"]


def test_exec_order_cycle(qtbot, ct):
    """Cyclic connections raise an error instead of a wrong order."""
    from mne_nodes.gui.node.node_viewer import NodeViewer

    viewer = NodeViewer(ct)
    qtbot.addWidget(viewer)
    in_node = viewer.add_input_node()
    filter_node = viewer.add_function_node("test_filter")
    filter_node2 = viewer.add_function_node("test_filter")
    in_node.output(port_idx=0).connect_to(filter_node.input(port_name="raw"))
    filter_node.output(port_name="raw").connect_to(filter_node2.input(port_name="raw"))
    filter_node2.output(port_name="raw").connect_to(filter_node.input(port_name="raw"))
    if not filter_node2.output(port_name="raw").connected(
        filter_node.input(port_name="raw")
    ):
        pytest.skip("Cyclic connections are prevented by the viewer.")
    with pytest.raises(RuntimeError, match="cycle"):
        viewer.get_node_sequence(in_node)


def test_multiple_func_nodes(nodeviewer):
    """Test adding multiple function nodes of the same type."""
    node1 = nodeviewer.node(node_name="test_filter")
    nodeviewer.add_function_node("test_filter")
    nodes = nodeviewer.get_node_by_function("test_filter")
    assert len(nodes) == 2
    node2 = nodeviewer.node(node_name="test_filter-1")
    assert node2 is not None
    # Make sure, that parameters are independent
    node1.parameter_guis["l_freq"].value = 0.5
    node2.parameter_guis["l_freq"].value = 1.0
    assert node1.parameter_guis["l_freq"].value != node2.parameter_guis["l_freq"].value
    assert nodeviewer.ct.parameter("l_freq", node1.name) != nodeviewer.ct.parameter(
        "l_freq", node2.name
    )


def test_node_resizes_and_autolayouts_on_proxywidget_resize(qtbot, ct):
    from mne_nodes.gui.node.node_viewer import NodeViewer

    nodeviewer = NodeViewer(ct)
    qtbot.addWidget(nodeviewer)
    node_a = nodeviewer.add_function_node("test_filter")
    node_b = nodeviewer.add_function_node("test_epochs")
    nodeviewer.auto_layout_nodes(nodes=[node_a, node_b])

    label = QLabel("Resize trigger")
    label.setFixedSize(180, 24)
    node_a.add_widget(label)
    node_a.draw_node()
    nodeviewer.auto_layout_nodes(nodes=[node_a, node_b])

    old_height = node_a.height
    old_gap = abs(node_b.y() - node_a.y())

    label.setFixedHeight(220)
    qtbot.waitUntil(lambda: node_a.height > old_height, timeout=2000)

    new_gap = abs(node_b.y() - node_a.y())
    assert new_gap > old_gap
