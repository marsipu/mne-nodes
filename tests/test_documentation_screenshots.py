"""Opt-in captures of real widgets for the documentation workflow."""

import json
import os
from importlib.resources import files
from pathlib import Path

import pytest
from qtpy.QtCore import Qt
from qtpy.QtGui import QImage

from mne_nodes.backend.controller import Controller, default_config
from mne_nodes.gui.gui_theme import set_app_font_size, set_app_theme
from mne_nodes.gui.main_window import MainWindow

pytestmark = pytest.mark.skipif(
    not os.environ.get("MNENODES_SCREENSHOT_DIR"),
    reason="Set MNENODES_SCREENSHOT_DIR to generate documentation screenshots.",
)


@pytest.fixture
def documentation_window(qtbot, qapp, settings, tmp_path):
    """Create a disposable pipeline using only bundled example data and code."""
    settings.set("app_theme", "light")
    settings.set("bids_root", Path(__file__).parent / "tiny_bids")
    previous_palette = qapp.palette()
    previous_font = qapp.font()
    previous_style = qapp.style().objectName()
    set_app_theme()
    set_app_font_size(12)
    pipeline = tmp_path / "documentation.json"
    pipeline.write_text(
        json.dumps({**default_config, "name": "Documentation demo"}),
        encoding="utf-8",
    )
    controller = Controller(config_path=pipeline, settings=settings)
    controller.load_plugin_path(
        Path(str(files("mne_nodes.resources") / "example_plugin_config.json"))
    )
    window = MainWindow(controller)
    qtbot.addWidget(window)
    window.resize(1200, 800)
    window.menuBar().setNativeMenuBar(False)
    window.finalize_controller_setup()
    viewer = window.viewer
    input_node = viewer.input_node
    assert input_node is not None
    filter_node = viewer.add_function_node("example_filter")
    source = input_node.output(port_name="eeg")
    destination = filter_node.input(port_name="raw")
    source.connect_to(destination)
    viewer.auto_layout_nodes()
    viewer.zoom_to_nodes()
    qtbot.waitExposed(window)
    assert source.connected(destination)
    assert set(filter_node.parameter_guis) == {"highpass", "lowpass"}
    try:
        yield window
    finally:
        window.close()
        qapp.setStyle(previous_style)
        qapp.setPalette(previous_palette)
        qapp.setFont(previous_font)


@pytest.mark.parametrize("scenario", ["pipeline", "node-picker"])
def test_documentation_screenshot(documentation_window, qtbot, scenario):
    """Capture ready widgets, normalize HiDPI sizes, and verify PNG round trips."""
    window = documentation_window
    if scenario == "pipeline":
        widget = window
        assert len(window.viewer.nodes) == 2
        assert window.statusBar().currentMessage() == "Documentation demo is ready."
    else:
        window.show_node_picker()
        widget = window.node_picker
        qtbot.addWidget(widget)
        widget.resize(900, 550)
        tree = widget.functions_view
        model = tree.model()
        category = model.index(0, 0)
        function = model.index(0, 0, category)
        assert model.data(function) == "example_filter"
        tree.setCurrentIndex(function)
        tree.resizeColumnToContents(0)
        tree.resizeColumnToContents(1)

    qtbot.waitExposed(widget)
    qtbot.waitUntil(lambda: widget.isVisible() and widget.width() > 0)
    widget.repaint()
    image = widget.grab().toImage()
    assert not image.isNull()
    image = image.scaled(
        widget.size(),
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    output = Path(os.environ["MNENODES_SCREENSHOT_DIR"]) / f"{scenario}.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    assert image.save(str(output), "PNG"), f"Could not save screenshot: {output}"
    saved = QImage(str(output))
    assert not saved.isNull()
    assert saved.size() == widget.size()
