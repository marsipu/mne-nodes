"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

from pprint import pprint

from qtpy.QtCore import QObject, QPoint, QPointF, Qt
from qtpy.QtWidgets import QLabel

from mne_nodes.conftest import _add_complex_nodes
from mne_nodes.gui.gui_utils import mouseDrag, mouseMove, mousePress, mouseRelease
from mne_nodes.gui.node.node_defaults import defaults
from mne_nodes.gui.node.ports import Port


def test_nodes_basic_interaction(nodeviewer):
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
    near_out1_pos = QPointF(out1_pos.x() + 6, out1_pos.y() + 4)
    mouseDrag(
        widget=nodeviewer.viewport(),
        positions=[in2_pos, near_out1_pos],
        button=Qt.MouseButton.LeftButton,
    )
    assert port1.connected(port2)


def test_nodes_click_to_click_connection(nodeviewer, qtbot):
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
    assert "Disconnect all" in action_texts


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
