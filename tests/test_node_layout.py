"""Regression tests for node placement and graph layout."""

from itertools import pairwise

import pytest
from qtpy.QtCore import QMimeData, QObject, QPointF, Qt
from qtpy.QtGui import QContextMenuEvent, QDropEvent, QPainterPathStroker
from qtpy.QtWidgets import QLabel

from mne_nodes.gui.node.base_node import BaseNode
from mne_nodes.gui.node.node_viewer import NodeViewer
from mne_nodes.gui.node.routing import separate_overlaps


@pytest.fixture
def viewer(ct, qtbot):
    """Provide an empty viewer without fitting its contents."""
    viewer = NodeViewer(ct)
    qtbot.addWidget(viewer)
    return viewer


def _node(viewer, name, size=None):
    node = BaseNode(
        viewer.ct,
        name=name,
        ports=[
            {"name": "raw", "port_type": "in", "multi_connection": True},
            {"name": "raw", "port_type": "out", "multi_connection": True},
        ],
    )
    if size is not None:
        label = QLabel(name)
        label.setFixedSize(*size)
        node.add_widget(label)
    return viewer.add_node(node)


def _connect(source, target):
    source.output(port_name="raw").connect_to(target.input(port_name="raw"))


def _obstructions(viewer):
    stroker = QPainterPathStroker()
    stroker.setWidth(2)
    return sum(
        stroker.createStroke(pipe.path()).intersects(node.sceneBoundingRect())
        for pipe in viewer.all_pipes()
        if pipe.input_port is not None and pipe.output_port is not None
        for node in viewer.nodes.values()
        if node not in (pipe.input_port.node, pipe.output_port.node)
    )


@pytest.mark.parametrize("port_type", ["in", "out"])
def test_connected_node_placement(viewer, port_type):
    anchor = _node(viewer, "anchor")
    anchor.setPos(300, 200)
    target = anchor.port(port_type=port_type, port_name="raw")
    new_type = "out" if port_type == "in" else "in"
    node = BaseNode(
        viewer.ct, name="new", ports=[{"name": "raw", "port_type": new_type}]
    )
    viewer.add_node(node, connected={"raw": {"type": new_type, "port_to": target}})
    new_rect = node.sceneBoundingRect()
    anchor_rect = anchor.sceneBoundingRect()
    if port_type == "in":
        gap = anchor_rect.left() - new_rect.right()
    else:
        gap = new_rect.left() - anchor_rect.right()
    assert gap == pytest.approx(viewer.default_x_distance)
    new_port = node.port(port_type=new_type, port_name="raw")
    assert new_port.sceneBoundingRect().center().y() == pytest.approx(
        target.sceneBoundingRect().center().y()
    )
    assert target.connected(new_port)


@pytest.mark.parametrize("port_type", ["in", "out"])
def test_port_menu_places_function_on_correct_side(viewer, monkeypatch, port_type):
    anchor = viewer.add_function_node("test_filter")
    target = anchor.port(port_type=port_type, port_name="raw")

    class Menu(QObject):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.actions = []

        def addMenu(self, title):
            return self

        def addAction(self, action):
            self.actions.append(action)

        def isEmpty(self):
            return not self.actions

        def exec(self, pos):
            next(a for a in self.actions if a.text() == "test_filter").trigger()

    monkeypatch.setattr("mne_nodes.gui.node.node_viewer.QMenu", Menu)
    pos = viewer.mapFromScene(target.sceneBoundingRect().center())
    event = QContextMenuEvent(
        QContextMenuEvent.Reason.Mouse, pos, viewer.viewport().mapToGlobal(pos)
    )
    rect = viewer.scene_rect()
    viewer._show_port_context_menu(target, event)
    new = viewer.node(node_name="test_filter-1")
    assert new is not None
    if port_type == "in":
        gap = anchor.sceneBoundingRect().left() - new.sceneBoundingRect().right()
    else:
        gap = new.sceneBoundingRect().left() - anchor.sceneBoundingRect().right()
    assert gap == pytest.approx(viewer.default_x_distance)
    assert viewer.scene_rect() == rect
    new_type = "out" if port_type == "in" else "in"
    assert target.connected(new.port(port_type=new_type, port_name="raw"))


@pytest.mark.parametrize("port_type", ["in", "out"])
def test_connected_placement_avoids_existing_nodes(viewer, port_type):
    anchor = _node(viewer, "anchor")
    blocker = _node(viewer, "blocker")
    sign = -1 if port_type == "in" else 1
    blocker.setPos(
        anchor.x() + sign * (anchor.width + viewer.default_x_distance), anchor.y()
    )
    target = anchor.port(port_type=port_type, port_name="raw")
    new_type = "out" if port_type == "in" else "in"
    new = BaseNode(
        viewer.ct, name="new", ports=[{"name": "raw", "port_type": new_type}]
    )
    viewer.add_node(new, connected={"raw": {"type": new_type, "port_to": target}})
    assert new.x() == blocker.x()
    assert new.sceneBoundingRect().top() - blocker.sceneBoundingRect().bottom() == (
        pytest.approx(viewer.default_y_distance)
    )
    assert not new.sceneBoundingRect().intersects(anchor.sceneBoundingRect())


def test_adding_function_preserves_view(viewer, qtbot):
    viewer.show()
    qtbot.waitExposed(viewer)
    viewer.set_scene_rect([120, 230, 900, 600])
    transform = viewer.transform()
    rect = viewer.scene_rect()
    origin = viewer.mapToScene(viewer.viewport().rect().center())
    node = viewer.add_function_node("test_filter")
    qtbot.wait(10)
    assert viewer.scene_rect() == rect
    assert viewer.transform() == transform
    assert viewer.mapToScene(viewer.viewport().rect().center()) == origin
    assert node.sceneBoundingRect().center() == origin


@pytest.mark.parametrize("plugins_loaded", [True, False])
def test_background_menu_auto_layout(viewer, monkeypatch, plugins_loaded):
    source, target = (_node(viewer, name) for name in ("source", "target"))
    _connect(source, target)
    target.setPos(-1000, 1000)
    if not plugins_loaded:
        monkeypatch.setattr(viewer.ct, "get_functions_categorized", dict)

    class Menu(QObject):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.actions = []

        def addMenu(self, title):
            return self

        def addAction(self, action):
            self.actions.append(action)

        def addSeparator(self):
            pass

        def isEmpty(self):
            return not self.actions

        def exec(self, pos):
            next(
                action
                for action in self.actions
                if action.text() == "&Auto-Layout Nodes"
            ).trigger()

    monkeypatch.setattr("mne_nodes.gui.node.node_viewer.QMenu", Menu)
    pos = viewer.mapFromScene(QPointF(3000, 3000))
    event = QContextMenuEvent(
        QContextMenuEvent.Reason.Mouse, pos, viewer.viewport().mapToGlobal(pos)
    )
    rect = viewer.scene_rect()
    transform = viewer.transform()
    viewer.contextMenuEvent(event)
    assert event.isAccepted()
    assert (
        target.sceneBoundingRect().left() - source.sceneBoundingRect().right()
    ) == pytest.approx(viewer.default_x_distance)
    assert viewer.scene_rect() == rect
    assert viewer.transform() == transform


@pytest.mark.parametrize(
    "payload", ["mne-nodes/function:test_filter", "mne-nodes/input:eeg"]
)
def test_dropping_node_preserves_view_and_position(viewer, payload):
    viewer.set_scene_rect([120, 230, 900, 600])
    rect = viewer.scene_rect()
    transform = viewer.transform()
    pos = QPointF(100, 150)
    expected = viewer.mapToScene(pos.toPoint())
    mime = QMimeData()
    mime.setText(payload)
    event = QDropEvent(
        pos,
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    viewer.dropEvent(event)
    assert event.isAccepted()
    assert viewer.scene_rect() == rect
    assert viewer.transform() == transform
    assert next(iter(viewer.nodes.values())).pos() == expected


def test_loading_nodes_preserves_saved_positions(nodeviewer):
    for index, node in enumerate(nodeviewer.nodes.values()):
        node.setPos(800 * (index + 1), 200 * (index + 1))
    positions = {node.name: node.pos() for node in nodeviewer.nodes.values()}
    config = nodeviewer.to_dict()
    nodeviewer.from_dict(config)
    assert {node.name: node.pos() for node in nodeviewer.nodes.values()} == positions


@pytest.mark.parametrize("down_stream", [True, False])
def test_layout_subset_does_not_move_other_nodes(viewer, down_stream):
    first, middle, last = (_node(viewer, name) for name in ("a", "b", "c"))
    _connect(first, middle)
    _connect(middle, last)
    last.setPos(2000, 1000)
    old_pos = last.pos()
    start_nodes = [first if down_stream else middle]
    original_starts = start_nodes.copy()
    viewer.auto_layout_nodes(
        [first, middle], down_stream=down_stream, start_nodes=start_nodes
    )
    assert last.pos() == old_pos
    assert start_nodes == original_starts
    assert middle.sceneBoundingRect().left() - first.sceneBoundingRect().right() == (
        pytest.approx(viewer.default_x_distance)
    )


@pytest.mark.parametrize("pipe_layout", ["straight", "curved", "angle", "routed"])
def test_layout_clears_shortcut_pipes(viewer, pipe_layout):
    viewer.pipe_layout = pipe_layout
    source, middle, sink = (_node(viewer, name) for name in ("a", "b", "c"))
    _connect(source, middle)
    _connect(middle, sink)
    _connect(source, sink)
    viewer.auto_layout_nodes()
    viewer.redraw_pipes()
    assert _obstructions(viewer) == 0
    for left, right in ((source, middle), (middle, sink)):
        assert right.sceneBoundingRect().left() - left.sceneBoundingRect().right() == (
            pytest.approx(viewer.default_x_distance)
        )


def test_layout_orders_branches_and_compacts_pipes(viewer):
    source_a, source_b, sink_b, sink_a = (
        _node(viewer, name) for name in ("source a", "source b", "sink b", "sink a")
    )
    _connect(source_a, sink_a)
    _connect(source_b, sink_b)
    viewer.auto_layout_nodes()
    assert (source_a.y() < source_b.y()) == (sink_a.y() < sink_b.y())
    assert _obstructions(viewer) == 0
    for source, sink in ((source_a, sink_a), (source_b, sink_b)):
        out_y = source.output(port_name="raw").sceneBoundingRect().center().y()
        in_y = sink.input(port_name="raw").sceneBoundingRect().center().y()
        assert out_y == pytest.approx(in_y)
    for layer in ((source_a, source_b), (sink_a, sink_b)):
        top, bottom = sorted(layer, key=lambda node: node.y())
        assert bottom.sceneBoundingRect().top() - top.sceneBoundingRect().bottom() == (
            pytest.approx(viewer.default_y_distance)
        )
    positions = [QPointF(node.pos()) for node in viewer.nodes.values()]
    viewer.auto_layout_nodes()
    assert [node.pos() for node in viewer.nodes.values()] == positions


def test_layout_uses_actual_sizes_and_preserves_center_and_view(viewer):
    nodes = [
        _node(viewer, "large", (350, 240)),
        _node(viewer, "small", (90, 40)),
        _node(viewer, "sink", (120, 80)),
        _node(viewer, "isolated", (160, 100)),
    ]
    _connect(nodes[0], nodes[2])
    _connect(nodes[1], nodes[2])
    center = viewer.nodes_rect_center(nodes)
    rect = viewer.scene_rect()
    transform = viewer.transform()
    viewer.auto_layout_nodes()
    assert viewer.nodes_rect_center(nodes) == pytest.approx(center)
    assert viewer.scene_rect() == rect
    assert viewer.transform() == transform
    layer = sorted([nodes[0], nodes[1], nodes[3]], key=lambda node: node.y())
    for top, bottom in pairwise(layer):
        assert bottom.sceneBoundingRect().top() - top.sceneBoundingRect().bottom() == (
            pytest.approx(viewer.default_y_distance)
        )
    assert nodes[2].sceneBoundingRect().left() - max(
        node.sceneBoundingRect().right() for node in layer
    ) == pytest.approx(viewer.default_x_distance)
    assert _obstructions(viewer) == 0


def test_routed_pipes_avoid_nodes(viewer, qtbot):
    source, blocker, sink = (_node(viewer, name) for name in ("a", "blocker", "c"))
    _connect(source, sink)
    source.setPos(0, 0)
    sink.setPos(source.width + 400, 0)
    blocker.setPos(source.width + 150, source.y() - 20)
    viewer.pipe_layout = "curved"
    assert _obstructions(viewer) > 0
    viewer.pipe_layout = "routed"
    assert _obstructions(viewer) == 0
    # Moving the blocker away re-routes the pipe once events are processed.
    blocker.setPos(0, 1000)
    qtbot.wait(10)
    pipe = next(iter(source.output(port_name="raw").connected_pipes.values()))
    assert pipe.path().boundingRect().height() < 5


def test_invalid_pipe_layout_falls_back(viewer):
    viewer.pipe_layout = "zigzag"
    assert viewer.pipe_layout == "curved"


def test_layout_minimizes_pipe_lengths(viewer):
    """A chain with side branches stays compact and mostly straight."""
    names = ["raw", "filter", "epochs", "evoked", "fwd", "inv", "stc", "src", "bem"]
    nodes = {name: _node(viewer, name) for name in names}
    for source, target in [
        ("raw", "filter"),
        ("filter", "epochs"),
        ("epochs", "evoked"),
        ("src", "fwd"),
        ("bem", "fwd"),
        ("fwd", "inv"),
        ("epochs", "inv"),
        ("inv", "stc"),
        ("evoked", "stc"),
    ]:
        _connect(nodes[source], nodes[target])
    for index, node in enumerate(nodes.values()):
        node.setPos(index * 37 % 500, index * 613 % 1700)
    viewer.auto_layout_nodes()
    lengths = []
    for pipe in viewer.all_pipes():
        if pipe.input_port is None or pipe.output_port is None:
            continue
        out_pos = pipe.output_port.sceneBoundingRect().center()
        in_pos = pipe.input_port.sceneBoundingRect().center()
        assert in_pos.x() > out_pos.x()
        lengths.append(abs(in_pos.y() - out_pos.y()))
    # Vertical offsets stay within roughly one node height per pipe.
    max_height = max(node.sceneBoundingRect().height() for node in nodes.values())
    assert sum(lengths) <= len(lengths) * max_height


def _collinear_overlaps(routes, tol=0.5):
    """Count overlapping collinear segment pairs of different routes."""
    segments = []
    for index, route in enumerate(routes):
        for a, b in pairwise(route):
            axis = 0 if abs(a[0] - b[0]) <= tol else 1
            low, high = sorted((a[1 - axis], b[1 - axis]))
            segments.append((index, axis, a[axis], low, high))
    return sum(
        1
        for i, (ri, axis_i, c_i, lo_i, hi_i) in enumerate(segments)
        for rj, axis_j, c_j, lo_j, hi_j in segments[i + 1 :]
        if ri != rj
        and axis_i == axis_j
        and abs(c_i - c_j) <= tol
        and min(hi_i, hi_j) - max(lo_i, lo_j) > tol
    )


def test_separate_overlaps_spreads_lanes():
    routes = [
        [(0, 0), (50, 0), (50, 100), (100, 100)],
        [(0, 20), (50, 20), (50, 200), (100, 200)],
        [(0, 300), (50, 300), (50, 400), (100, 400)],
    ]
    assert _collinear_overlaps(routes) == 1
    separated = separate_overlaps(routes, padding=8)
    assert _collinear_overlaps(separated) == 0
    xs = sorted(separated[i][1][0] for i in (0, 1))
    assert xs == pytest.approx([46, 54])
    # Port stubs keep their start and end points, the lone route is unchanged.
    for old, new in zip(routes, separated, strict=True):
        assert new[0] == old[0]
        assert new[-1] == old[-1]
    assert separated[2] == routes[2]
    limited = separate_overlaps(routes, padding=8, max_offset=2)
    assert sorted(limited[i][1][0] for i in (0, 1)) == pytest.approx([48, 52])


def test_routed_pipes_do_not_overlap(viewer):
    viewer.pipe_layout = "routed"
    sources = [_node(viewer, f"source {i}") for i in range(3)]
    sinks = [_node(viewer, f"sink {i}") for i in range(3)]
    blocker = _node(viewer, "blocker", (60, 400))
    for index, (source, sink) in enumerate(zip(sources, sinks, strict=True)):
        source.setPos(0, index * 120)
        sink.setPos(600, 300 - index * 120)
        _connect(source, sink)
    blocker.setPos(300, -50)
    viewer.redraw_pipes()
    pipes = [
        pipe
        for pipe in viewer.all_pipes()
        if pipe.input_port is not None and pipe.output_port is not None
    ]
    routes = [pipe._route for pipe in pipes]
    assert all(routes)
    assert _collinear_overlaps(routes) == 0
    assert _obstructions(viewer) == 0


def test_routed_pipes_reroute_after_drag(viewer, qtbot):
    source, blocker, sink = (_node(viewer, name) for name in ("a", "blocker", "c"))
    _connect(source, sink)
    sink.setPos(source.width + 400, 0)
    blocker.setPos(0, 1000)
    viewer.pipe_layout = "routed"
    pipe = next(iter(source.output(port_name="raw").connected_pipes.values()))
    straight = list(pipe._route)
    # Dragging the blocker into the pipe does not re-route until release.
    viewer._nodes_moving = True
    viewer._press_node_positions = {n: n.pos() for n in viewer.nodes.values()}
    blocker.setPos(source.width + 150, -20)
    qtbot.wait(10)
    assert pipe._route == straight
    assert _obstructions(viewer) > 0
    # Moving both connected nodes together translates the route.
    for node in (source, sink):
        node.setPos(node.x(), node.y() + 500)
    qtbot.wait(10)
    assert pipe.path().boundingRect().top() == pytest.approx(
        min(y for _, y in straight) + 500
    )
    viewer._finish_node_move()
    qtbot.wait(10)
    assert not viewer.nodes_moving
    assert _obstructions(viewer) == 0
