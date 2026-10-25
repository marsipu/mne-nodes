"""Tests for the shared semantic palette and output-port integration."""

import pytest
from qtpy.QtGui import QColor, QImage, QPainter, QPalette
from qtpy.QtWidgets import QStyle, QStyleOptionTabWidgetFrame, QWidget

from mne_nodes.gui.colors import (
    ACCENT_OPACITY,
    ACTIVE_ACCENT_OPACITY,
    CATEGORY_COLORS,
    CATEGORY_DATATYPES,
    DATATYPE_CATEGORIES,
    datatype_color,
)
from mne_nodes.gui.node.input_node import DatatypeTabBar, DatatypeTabWidget, InputWidget
from mne_nodes.gui.node.node_defaults import defaults


@pytest.mark.parametrize(
    ("category", "color"),
    [
        ("raw_sensor", "#fce104"),
        ("processed_sensor", "#e6441a"),
        ("raw_source", "#3348cd"),
        ("processed_source", "#01feff"),
    ],
)
def test_semantic_palette_assignments(category, color):
    """Every registered datatype uses its category's exact requested HEX color."""
    assert CATEGORY_COLORS[category] == color
    for datatype in CATEGORY_DATATYPES[category]:
        assert datatype_color(datatype) == color
    all_types = [name for names in CATEGORY_DATATYPES.values() for name in names]
    assert len(all_types) == len(DATATYPE_CATEGORIES)


@pytest.mark.parametrize(
    ("datatype", "aliases", "expected"),
    [
        ("MEG", [], "#fce104"),
        ("epochs", ["raw"], "#e6441a"),
        ("anat", [], "#3348cd"),
        ("forward", [], "#01feff"),
        ("custom_result", ["evoked", "epochs"], "#e6441a"),
        ("custom_result", ["raw", "stc"], None),
        ("custom_result", ["unknown"], None),
    ],
)
def test_datatype_color_resolution(datatype, aliases, expected):
    """Own types take priority; mixed semantic aliases are not guessed."""
    assert datatype_color(datatype, aliases) == expected


@pytest.mark.parametrize(
    ("datatype", "color"),
    [
        ("eeg", "#fce104"),
        ("epochs", "#e6441a"),
        ("subject", "#3348cd"),
        ("sourceestimate", "#01feff"),
    ],
)
@pytest.mark.parametrize("state", ["idle", "hovered", "connected"])
def test_output_port_paints_semantic_color(nodeviewer, datatype, color, state):
    """Actual painting retains category colors while hovered or connected."""
    function = nodeviewer.node(node_name="test_filter")
    port = function.add_output(datatype, accepted_ports=[datatype])
    port.hovered = state == "hovered"
    if state == "connected":
        target = nodeviewer.input_node.add_input(datatype, accepted_ports=[datatype])
        port.connect_to(target)
        assert port.connected(target)
    image = QImage(60, 40, QImage.Format.Format_ARGB32)
    image.fill(QColor("transparent"))
    painter = QPainter(image)
    port.paint(painter, None, None)
    painter.end()
    center = port.boundingRect().center().toPoint()
    painted_colors = {
        image.pixelColor(x, y).name()
        for x in range(image.width())
        for y in range(image.height())
        if image.pixelColor(x, y).alpha() > 0
    }
    assert color in painted_colors
    if state != "idle":
        assert image.pixelColor(center).name() != color
    assert QColor(*port.active_color).name() == color
    assert QColor(*port.hover_color).name() == color


def test_palette_applies_to_input_node_outputs_and_fallbacks(nodeviewer):
    """Input-node outputs use the registry; unclassified ports keep defaults."""
    node = nodeviewer.input_node
    assert QColor(*node.output(port_name="eeg").color).name() == "#fce104"
    assert QColor(*node.output(port_name="subject").color).name() == "#3348cd"
    assert QColor(*node.output(port_name="trans").color).name() == "#01feff"
    function = nodeviewer.node(node_name="test_filter")
    custom = function.add_output("custom", accepted_ports=["epochs"])
    assert QColor(*custom.color).name() == "#e6441a"
    custom.accepted_ports = []
    custom.update_datatype_color()
    assert custom.color == defaults["ports"]["color"]
    assert function.input(port_name="raw").color == defaults["ports"]["color"]


def test_input_outputs_ordered_by_processing_category(nodeviewer, monkeypatch):
    """Category ordering survives refresh without replacing ports or connections."""
    node = nodeviewer.input_node
    ct = nodeviewer.ct
    expected = [
        "eeg",
        "meg",
        "ieeg",
        "info",
        "event_id",
        "raw_er",
        "epochs",
        "evoked",
        "subject",
        "anat",
        "trans",
        "stc",
        "custom",
    ]
    monkeypatch.setattr(ct, "get_datatypes", lambda: list(reversed(expected)))
    monkeypatch.setattr(ct, "input_output_availability", lambda **kwargs: {})
    monkeypatch.setattr(ct, "get_datatype_items", lambda datatype: ["available"])
    monkeypatch.setattr(node.input_widget, "update_widgets", lambda: None)
    source = node.output(port_name="eeg")
    target = nodeviewer.node(node_name="test_filter").input(port_name="raw")
    source.connect_to(target)
    for _ in range(2):
        node.update_widgets()
        assert [port.name for port in node.outputs] == expected
        assert node.output(port_name="eeg") is source
        assert source.connected(target)
        assert [port.y() for port in node.outputs] == sorted(
            port.y() for port in node.outputs
        )
    ports = node.outputs
    monkeypatch.setattr(ct, "get_datatypes", lambda: expected)
    node.update_widgets()
    assert node.outputs == ports


def test_input_output_order_survives_legacy_pipeline_load(nodeviewer):
    """Older saved port order is normalized when the input node is restored."""
    node = nodeviewer.input_node
    expected = [port.name for port in node.outputs]
    config = nodeviewer.to_dict()
    saved_input = next(
        data for data in config["nodes"].values() if data["class"] == "InputNode"
    )
    saved_input["ports"] = dict(reversed(list(saved_input["ports"].items())))
    nodeviewer.load_nodes(config)
    assert [port.name for port in nodeviewer.input_node.outputs] == expected
    assert nodeviewer.input_node.output(port_name="eeg").connected_ports


@pytest.mark.parametrize("background", ["#eeeeee", "#232323"])
@pytest.mark.parametrize("selected", [0, 1])
def test_datatype_tabs_paint_only_muted_accents(qtbot, background, selected):
    """Semantic colors must affect only the small accent, not native tab styling."""
    bar = DatatypeTabBar()
    qtbot.addWidget(bar)
    palette = bar.palette()
    palette.setColor(QPalette.ColorRole.Window, QColor(background))
    palette.setColor(QPalette.ColorRole.Button, QColor(background))
    bar.setPalette(palette)
    datatypes = ["eeg", "epochs", "anat", "stc", "unknown", None]
    for datatype in datatypes:
        bar.addTab(datatype or "Groups")
    bar.setCurrentIndex(selected)
    bar.resize(bar.sizeHint())
    bar.show()
    baseline = bar.grab().toImage()
    for index, datatype in enumerate(datatypes):
        bar.setTabData(index, datatype)
    decorated = bar.grab().toImage()
    scale = decorated.devicePixelRatio()
    for index, datatype in enumerate(datatypes):
        tab = bar.tabRect(index)
        color = datatype_color(datatype) if datatype else None
        accent = tab.adjusted(8, 0, -8, -3)
        accent.setTop(accent.bottom() - 1)
        changed = 0
        for x in range(tab.left(), tab.right() + 1):
            for y in range(tab.top(), tab.bottom() + 1):
                before = baseline.pixelColor(int(x * scale), int(y * scale))
                after = decorated.pixelColor(int(x * scale), int(y * scale))
                if before != after:
                    assert color is not None
                    assert accent.contains(x, y)
                    changed += 1
        if color is None:
            assert changed == 0
            continue
        assert changed > 0
        point = accent.center()
        before = baseline.pixelColor(int(point.x() * scale), int(point.y() * scale))
        after = decorated.pixelColor(int(point.x() * scale), int(point.y() * scale))
        opacity = ACTIVE_ACCENT_OPACITY if index == selected else ACCENT_OPACITY
        source = QColor(color)
        for channel in ("red", "green", "blue"):
            expected = round(
                getattr(source, channel)() * opacity
                + getattr(before, channel)() * (1 - opacity)
            )
            assert abs(getattr(after, channel)() - expected) <= 2


def test_input_tab_datatypes_survive_refresh(ct, qtbot, monkeypatch):
    """Accents follow the tab datatype when dataset tabs are rebuilt."""
    items = {"eeg": [], "anat": []}
    monkeypatch.setattr(ct, "get_all_datatype_items", lambda: items)
    widget = InputWidget(ct)
    qtbot.addWidget(widget)
    assert isinstance(widget.tab_widget.tabBar(), DatatypeTabBar)
    for expected in (["eeg", "anat", None], ["meg", None]):
        widget.update_widgets()
        bar = widget.tab_widget.tabBar()
        assert [bar.tabData(index) for index in range(bar.count())] == expected
        assert bar.tabText(bar.count() - 1) == "Groups"
        items = {"meg": []}


@pytest.mark.parametrize("background", ["#eeeeee", "#232323"])
def test_datatype_page_frame_follows_selection(qtbot, background):
    """Only the frame is tinted, and neutral tabs remove the previous tint."""
    widget = DatatypeTabWidget()
    qtbot.addWidget(widget)
    palette = widget.palette()
    palette.setColor(QPalette.ColorRole.Window, QColor(background))
    palette.setColor(QPalette.ColorRole.Button, QColor(background))
    widget.setPalette(palette)
    for name in ("meg", "anat", "Groups", "unknown"):
        widget.addTab(QWidget(), name)
    widget.resize(400, 300)
    widget.show()
    option = QStyleOptionTabWidgetFrame()
    widget.initStyleOption(option)
    frame = widget.style().subElementRect(
        QStyle.SubElement.SE_TabWidgetTabPane, option, widget
    )
    for index, datatype in enumerate(("meg", "anat", None, "unknown")):
        widget.setCurrentIndex(index)
        baseline = widget.grab().toImage()
        widget.tabBar().setTabData(index, datatype)
        decorated = widget.grab().toImage()
        scale = decorated.devicePixelRatio()
        for point in (
            frame.topLeft() + (frame.bottomLeft() - frame.topLeft()) / 2,
            frame.topRight() + (frame.bottomRight() - frame.topRight()) / 2,
            frame.bottomLeft() + (frame.bottomRight() - frame.bottomLeft()) / 2,
        ):
            before = baseline.pixelColor(int(point.x() * scale), int(point.y() * scale))
            after = decorated.pixelColor(int(point.x() * scale), int(point.y() * scale))
            color = datatype_color(datatype) if datatype else None
            if color is None:
                assert after == before
            else:
                assert after != before, (datatype, point, frame)
                source = QColor(color)
                for channel in ("red", "green", "blue"):
                    expected = round(
                        getattr(source, channel)() * ACCENT_OPACITY
                        + getattr(before, channel)() * (1 - ACCENT_OPACITY)
                    )
                    assert abs(getattr(after, channel)() - expected) <= 2
        center = frame.center()
        assert decorated.pixelColor(
            int(center.x() * scale), int(center.y() * scale)
        ) == baseline.pixelColor(int(center.x() * scale), int(center.y() * scale))
