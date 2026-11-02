"""Regression tests for node placement and graph layout."""

from itertools import combinations

import pytest
from qtpy.QtCore import QPointF
from qtpy.QtGui import QPainterPathStroker
from qtpy.QtWidgets import QLabel

from mne_nodes.gui.node.base_node import BaseNode
from mne_nodes.gui.node.node_viewer import NodeViewer
from mne_nodes.gui.widget_registry import widget_registry


@pytest.fixture
def viewer(ct, qtbot):
    """Provide an empty viewer without fitting its contents."""
    viewer = NodeViewer(ct)
    qtbot.addWidget(viewer)
    yield viewer
    widget_registry().unregister("viewer", viewer)


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


def _pipes(viewer):
    return [
        pipe
        for pipe in viewer.all_pipes()
        if pipe.input_port is not None and pipe.output_port is not None
    ]


def _obstructions(viewer):
    stroker = QPainterPathStroker()
    stroker.setWidth(2)
    return sum(
        stroker.createStroke(pipe.path()).intersects(node.sceneBoundingRect())
        for pipe in _pipes(viewer)
        for node in viewer.nodes.values()
        if node not in (pipe.input_port.node, pipe.output_port.node)
    )


def test_auto_layout(viewer):
    """Auto-layout yields a stable, left-to-right, non-overlapping graph."""
    names = ["raw", "filter", "epochs", "evoked", "fwd", "inv", "stc", "src", "bem"]
    sizes = {"fwd": (350, 240), "src": (90, 40)}
    nodes = {name: _node(viewer, name, sizes.get(name)) for name in names}
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
    for pipe in _pipes(viewer):
        out_pos = pipe.output_port.sceneBoundingRect().center()
        assert pipe.input_port.sceneBoundingRect().center().x() > out_pos.x()
    for first, second in combinations(nodes.values(), 2):
        assert not first.sceneBoundingRect().intersects(second.sceneBoundingRect())
    assert _obstructions(viewer) == 0
    positions = [QPointF(node.pos()) for node in nodes.values()]
    viewer.auto_layout_nodes()
    assert [node.pos() for node in nodes.values()] == positions
