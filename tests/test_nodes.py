"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

from copy import deepcopy

import pytest
from qtpy.QtCore import QPointF, Qt

from mne_nodes.gui.gui_utils import mouseDrag
from mne_nodes.gui.node.ports import Port


def test_input_outputs_require_selection(nodeviewer):
    """Outputs are enabled by selections; metadata outputs are not selectable."""
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
    tabs = {
        node.input_widget.tab_widget.tabText(index)
        for index in range(node.input_widget.tab_widget.count())
    }
    assert {"eeg", "Groups"} <= tabs
    for data_type in ("event_id", "info", "trans", "subject"):
        assert node.output(port_name=data_type).accepted_ports == [data_type]
        assert data_type not in tabs


def test_same_root_refresh_preserves_selections_connections_and_output_settings(
    nodeviewer, monkeypatch
):
    """Rescanning the active dataset must not behave like switching datasets."""
    from mne_bids import get_bids_path_from_fname

    ct = nodeviewer.ct
    node = nodeviewer.input_node
    recording = get_bids_path_from_fname(next(ct.bids_root.rglob("*_eeg.vhdr")))
    ct.input_selection_changed([recording.basename], "eeg")
    ct.set("custom_groups", {"existing": [recording.basename]})
    derivative = ct.ensure_deriv_root()
    port = node.output(port_name="eeg")
    connections = list(port.connected_ports)
    assert connections
    anatomy = recording.copy().update(
        datatype="anat", task=None, suffix="T1w", extension=".nii.gz"
    )
    anatomy.directory.mkdir(parents=True, exist_ok=True)
    anatomy.fpath.touch()

    def unexpected_prompt(*args, **kwargs):
        pytest.fail("Reselecting the active root must not request a state reset.")

    monkeypatch.setattr("mne_nodes.backend.controller.ask_user", unexpected_prompt)
    ct.bids_root = ct.bids_root
    assert ct.get("selected_inputs")["eeg"] == [recording.basename]
    assert ct.get("custom_groups") == {"existing": [recording.basename]}
    assert ct.deriv_root == derivative
    assert node.output(port_name="eeg") is port
    assert port.connected_ports == connections
    assert port.isEnabled()
    assert node.output(port_name="anat") is not None


def test_rebuilding_input_checklists_removes_hidden_stale_selections(
    nodeviewer, caplog
):
    """A previous dataset's invisible checked files cannot block current outputs."""
    ct = nodeviewer.ct
    node = nodeviewer.input_node
    recording = ct.get_datatype_items("eeg")[0]
    ct.set(
        "selected_inputs",
        {
            "eeg": ["sub-absent_task-rest_eeg.vhdr", recording],
            "anat": ["sub-absent_T1w.nii.gz"],
        },
    )
    ct.refresh_input_outputs()
    assert not node.output(port_name="eeg").isEnabled()
    node.update_widgets()
    assert ct.get("selected_inputs")["eeg"] == [recording]
    assert not ct.get("selected_inputs")["anat"]
    assert node.output(port_name="eeg").isEnabled()
    assert node.output(port_name="info").isEnabled()
    assert "sub-absent_task-rest_eeg.vhdr" in caplog.text
    tabs = node.input_widget.tab_widget
    widget = next(
        tabs.widget(index)
        for index in range(tabs.count())
        if tabs.tabText(index) == "eeg"
    )
    widget.clear_all()
    assert not node.output(port_name="eeg").isEnabled()
    widget.select_all()
    assert ct.get("selected_inputs")["eeg"] == ct.get_datatype_items("eeg")
    assert node.output(port_name="eeg").isEnabled()


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


def test_port_connections(nodeviewer):
    """Connect by mouse, validate port types, slice wires and delete nodes."""
    ct = nodeviewer.ct
    ct.input_selection_changed(ct.get_datatype_items("eeg")[:1], "eeg")
    node1 = nodeviewer.input_node
    node2 = nodeviewer.node(node_name="test_filter")
    evokeds = nodeviewer.add_function_node("test_evokeds")
    port1 = node1.output(port_name="eeg")
    port2 = node2.input(port_name="raw")
    assert port1.connected(port2)
    port1.disconnect_from(port2)
    assert not port1.connected(port2)
    assert nodeviewer._ports_can_connect(port1, port2)
    assert not nodeviewer._ports_can_connect(port1, evokeds.input(port_name="epochs"))
    assert not nodeviewer._ports_can_connect(port1, node2.output(port_name="raw"))
    # Create connection by mouse
    out1_pos = nodeviewer.port_position_view(node_id=node1.id, port_id=port1.id)
    in2_pos = nodeviewer.port_position_view(node_id=node2.id, port_id=port2.id)
    mouseDrag(
        widget=nodeviewer.viewport(),
        positions=[out1_pos, in2_pos],
        button=Qt.MouseButton.LeftButton,
    )
    assert port1.connected(port2)
    # Slice the connection
    mouseDrag(
        widget=nodeviewer.viewport(),
        positions=[
            QPointF(out1_pos.x() + 20, out1_pos.y() - 20),
            QPointF(in2_pos.x() - 20, in2_pos.y() + 20),
        ],
        button=Qt.MouseButton.LeftButton,
        modifier=Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    assert not port1.connected(port2)
    # Deleting a node removes its connections
    port1.connect_to(port2)
    nodeviewer.remove_node(node2)
    assert nodeviewer.node(node_name="test_filter") is None
    assert port2 not in port1.connected_ports


def test_node_serialization(nodeviewer):
    """Round-trip the node graph, including positions and blocked wiring."""
    ct = nodeviewer.ct
    ct.function_meta["test_filter"]["inputs"]["trans"] = {
        "accepted_ports": ["trans"],
        "optional": False,
    }
    function = nodeviewer.node(node_name="test_filter")
    target = function.add_input("trans", accepted_ports=["trans"])
    trans = nodeviewer.input_node.output(port_name="trans")
    # Restore-style connections bypass interactive availability checks.
    trans.connect_to(target)
    assert not nodeviewer._ports_can_connect(trans, target)
    for index, node in enumerate(nodeviewer.nodes.values()):
        node.setPos(800 * (index + 1), 200 * (index + 1))
    positions = {node.name: node.pos() for node in nodeviewer.nodes.values()}
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
    assert {node.name: node.pos() for node in nodeviewer.nodes.values()} == positions
    trans = input_node.output(port_name="trans")
    assert not trans.isEnabled()
    assert len(trans.connected_ports) == 1


def test_exec_order(qtbot, ct):
    """Respect upstream chains, run side-effect branches first, reject cycles."""
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

    # Side-effect-only nodes run before output-producing sibling branches.
    side_effect_meta = deepcopy(ct.get_function_meta("test_filter"))
    side_effect_meta["outputs"] = {}
    ct.function_meta["test_side_effect"] = side_effect_meta
    side_viewer = NodeViewer(ct)
    qtbot.addWidget(side_viewer)
    side_in = side_viewer.add_input_node().output(port_idx=0)
    for name in ("test_filter", "test_side_effect"):
        node = side_viewer.add_function_node(name)
        side_in.connect_to(node.input(port_name="raw"))
    order = [
        description["name"]
        for description in side_viewer.get_node_sequence(side_in.node)["file"]
    ]
    assert order.index("test_side_effect") < order.index("test_filter")

    # Cyclic connections raise an error instead of a wrong order.
    filter_out = filter_node.output(port_name="raw")
    loop_node = viewer.add_function_node("test_filter")
    filter_out.connect_to(loop_node.input(port_name="raw"))
    loop_node.output(port_name="raw").connect_to(filter_node.input(port_name="raw"))
    assert loop_node.output(port_name="raw").connected(
        filter_node.input(port_name="raw")
    )
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
