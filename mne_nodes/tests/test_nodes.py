from pprint import pprint

from qtpy.QtCore import QPointF, Qt
from qtpy.QtWidgets import QLabel

from mne_nodes.conftest import _add_complex_nodes
from mne_nodes.gui.gui_utils import mouseDrag
from mne_nodes.gui.node.node_viewer import NodeViewer


def test_nodes_basic_interaction(nodeviewer):
    node1 = nodeviewer.get_node_by_input()
    node2 = nodeviewer.node(node_name="filter_data")
    port1 = node1.output(port_name="raw")
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


def test_node_serialization(nodeviewer):
    """Test serialization and deserialization of NodeViewer."""
    viewer_dict = nodeviewer.to_dict()
    nodeviewer.clear()
    nodeviewer.from_dict(viewer_dict)
    second_viewer_dict = nodeviewer.to_dict()
    assert len(viewer_dict["nodes"]) == len(second_viewer_dict["nodes"])


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
    viewer = NodeViewer(ct)
    qtbot.addWidget(viewer)
    _add_complex_nodes(viewer)

    n = viewer.node(node_idx=0)
    eo = viewer.get_node_sequence(n)
    pprint("first node:")
    pprint(eo)

    n = viewer.node(node_name="filter_bandpass")
    eo = viewer.get_node_sequence(n)
    pprint("filter_data:")
    pprint(eo)

    n = viewer.node(node_name="create_epochs")
    eo = viewer.get_node_sequence(n)
    pprint("epoch_raw:")
    pprint(eo)

    viewer.show()


def test_multiple_func_nodes(nodeviewer):
    """Test adding multiple function nodes of the same type."""
    node1 = nodeviewer.node(node_name="filter_data")
    nodeviewer.add_function_node("filter_data")
    nodes = nodeviewer.get_node_by_function("filter_data")
    assert len(nodes) == 2
    node2 = nodeviewer.node(node_name="filter_data-1")
    assert node2 is not None
    # Make sure, that parameters are independent
    node1.parameter_guis["lowpass"].value = 0.5
    node2.parameter_guis["lowpass"].value = 1.0
    assert (
        node1.parameter_guis["lowpass"].value != node2.parameter_guis["lowpass"].value
    )
    assert nodeviewer.ct.parameter("lowpass", node1.name) != nodeviewer.ct.parameter(
        "lowpass", node2.name
    )


def test_node_resizes_and_autolayouts_on_proxywidget_resize(qtbot, ct):
    nodeviewer = NodeViewer(ct)
    qtbot.addWidget(nodeviewer)
    node_a = nodeviewer.add_function_node("filter_data")
    node_b = nodeviewer.add_function_node("find_events")
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
