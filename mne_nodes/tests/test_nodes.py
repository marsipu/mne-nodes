from mne_nodes.gui.gui_utils import mouseDrag
from qtpy.QtCore import Qt, QPointF


def test_nodes_basic_interaction(nodeviewer):
    node1 = nodeviewer.input_node()
    node2 = nodeviewer.function_node("filter_data")
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


def test_show_nodeviewer(qtbot, nodeviewer_extended):
    """Test if NodeViewer can be shown."""
    nodeviewer = nodeviewer_extended
    nodeviewer.show()
    assert nodeviewer.isVisible()

    # Check if the viewport is correctly set
    assert nodeviewer.viewport() is not None

    # Check if the nodes are correctly laid out
    assert len(nodeviewer.nodes) > 0
    for node in nodeviewer.nodes.values():
        assert node.isVisible()
