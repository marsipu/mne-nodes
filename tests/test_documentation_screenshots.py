"""Opt-in captures of real widgets for the documentation workflow."""

import json
import os
import shutil
from importlib.resources import files
from pathlib import Path

import mne
import pytest
from mne_bids import BIDSPath
from qtpy.QtCore import QProcess, QSize, Qt
from qtpy.QtGui import QImage

from mne_nodes.backend.controller import Controller, default_config
from mne_nodes.backend.coregistration import CoregGroup, CoregRecording
from mne_nodes.backend.execution import Process
from mne_nodes.backend.plugin_package import PluginPackageMetadata
from mne_nodes.gui.dialogs.coreg_dialog import CoregDialog
from mne_nodes.gui.function_widgets import FunctionImporter
from mne_nodes.gui.gui_theme import set_app_font_size, set_app_theme
from mne_nodes.gui.main_window import MainWindow

pytestmark = pytest.mark.skipif(
    not os.environ.get("MNENODES_SCREENSHOT_DIR"),
    reason="Set MNENODES_SCREENSHOT_DIR to generate documentation screenshots.",
)


@pytest.fixture
def documentation_window(qtbot, qapp, settings, tmp_path, monkeypatch):
    """Create a disposable pipeline using only bundled example data and code."""
    settings.set("app_theme", "light")
    settings.set("keep_plots_open", False)
    monkeypatch.setenv("MNENODES_DEBUG", "false")
    monkeypatch.setattr(
        Controller, "run_script_folder", property(lambda self: tmp_path)
    )
    monkeypatch.setattr(
        "mne_nodes.gui.console.Process",
        lambda **kwargs: Process(**{**kwargs, "self_destruct": False}),
    )
    bids_root = tmp_path / "bids"
    shutil.copytree(Path(__file__).parent / "tiny_bids", bids_root)
    settings.set("bids_root", bids_root)
    previous_palette = qapp.palette()
    previous_font = qapp.font()
    previous_style = qapp.style().objectName()
    set_app_theme()
    set_app_font_size(12)
    pipeline = tmp_path / "documentation.json"
    pipeline.write_text(
        json.dumps({**default_config, "name": "Documentation demo"}), encoding="utf-8"
    )
    controller = Controller(config_path=pipeline, settings=settings)
    controller.load_plugin_path(
        Path(str(files("mne_nodes.resources") / "example_plugin_config.json"))
    )
    demo_code = """import mne


def prepare_eeg(raw, resample=200):
    \"\"\"Use synthetic sensor positions for this source-analysis example.\"\"\"
    raw = raw.copy().load_data().pick(["Fp1", "Fp2", "F3", "F4", "C3", "C4", "P3", "P4"])
    positions = {
        "Fp1": (-0.03, 0.075, 0.03), "Fp2": (0.03, 0.075, 0.03),
        "F3": (-0.04, 0.04, 0.07), "F4": (0.04, 0.04, 0.07),
        "C3": (-0.06, 0.0, 0.07), "C4": (0.06, 0.0, 0.07),
        "P3": (-0.04, -0.04, 0.07), "P4": (0.04, -0.04, 0.07),
    }
    raw.set_montage(mne.channels.make_dig_montage(ch_pos=positions, coord_frame="head"))
    raw.set_eeg_reference("average", projection=True)
    raw.resample(resample)
    return raw


def create_epochs(raw, duration=0.4):
    \"\"\"Create fixed-length epochs for an interface demonstration.\"\"\"
    epochs = mne.make_fixed_length_epochs(raw, duration=duration, preload=True)
    return epochs


def average_epochs(epochs, picks="eeg"):
    \"\"\"Average epochs for an interface demonstration.\"\"\"
    evoked = epochs.average(picks=picks)
    return evoked


def noise_covariance(epochs, method="empirical"):
    \"\"\"Estimate covariance from the same short example recording.\"\"\"
    cov = mne.compute_covariance(epochs, method=method)
    return cov


def spherical_forward(raw, spacing=40.0):
    \"\"\"Create a coarse spherical model; it is not an anatomical fit.\"\"\"
    sphere = mne.make_sphere_model(r0=(0, 0, 0), head_radius=0.09)
    src = mne.setup_volume_source_space(
        subject=None, pos=spacing, sphere=(0, 0, 0, 0.08), exclude=20.0, verbose=False
    )
    forward = mne.make_forward_solution(raw.info, trans=None, src=src, bem=sphere,
                                        eeg=True, meg=False, verbose=False)
    return forward


def estimate_sources(evoked, cov, forward, snr=3.0):
    \"\"\"Compute an illustrative minimum-norm source estimate.\"\"\"
    inverse = mne.minimum_norm.make_inverse_operator(evoked.info, forward, cov,
                                                     loose=1.0, depth=None)
    stc = mne.minimum_norm.apply_inverse(evoked, inverse, lambda2=1.0 / snr**2,
                                         method="MNE")
    return stc
"""
    importer = FunctionImporter(
        code=demo_code,
        plugin_name="documentation_processing",
        destination_dir=tmp_path,
        on_saved=controller.load_plugin_path,
        package_metadata=PluginPackageMetadata(
            distribution_name="mne-nodes_documentation-processing",
            description="Disposable documentation workflow",
            author="mne-nodes contributors",
            license_expression="BSD-3-Clause",
        ),
    )
    qtbot.addWidget(importer)
    assert importer.save()
    recordings = controller.get_datatype_items("eeg")
    selected = next(name for name in recordings if name.endswith(".vhdr"))
    controller.input_selection_changed([selected], data_type="eeg")
    window = MainWindow(controller)
    qtbot.addWidget(window)
    window.setFixedSize(1800, 900)
    window.menuBar().setNativeMenuBar(False)
    window.finalize_controller_setup()
    viewer = window.viewer
    input_node = viewer.input_node
    assert input_node is not None
    filter_node = viewer.add_function_node("example_filter")
    filter_node.parameter_guis["highpass"].value = 5
    prepare_node = viewer.add_function_node("prepare_eeg")
    epochs_node = viewer.add_function_node("create_epochs")
    average_node = viewer.add_function_node("average_epochs")
    covariance_node = viewer.add_function_node("noise_covariance")
    forward_node = viewer.add_function_node("spherical_forward")
    source_node = viewer.add_function_node("estimate_sources")
    source = input_node.output(port_name="eeg")
    destination = prepare_node.input(port_name="raw")
    source.connect_to(destination)
    prepare_node.output(port_name="raw").connect_to(filter_node.input(port_name="raw"))
    filter_node.output(port_name="raw").connect_to(epochs_node.input(port_name="raw"))
    epochs_node.output(port_name="epochs").connect_to(
        average_node.input(port_name="epochs")
    )
    epochs_node.output(port_name="epochs").connect_to(
        covariance_node.input(port_name="epochs")
    )
    prepare_node.output(port_name="raw").connect_to(forward_node.input(port_name="raw"))
    average_node.output(port_name="evoked").connect_to(
        source_node.input(port_name="evoked")
    )
    covariance_node.output(port_name="cov").connect_to(
        source_node.input(port_name="cov")
    )
    forward_node.output(port_name="forward").connect_to(
        source_node.input(port_name="forward")
    )
    viewer.auto_layout_nodes()
    viewer.zoom_to_nodes()
    qtbot.waitExposed(window)
    viewer.ensure_visible(viewer._combined_rect(viewer.nodes.values()))
    visible = viewer.mapToScene(viewer.viewport().rect()).boundingRect()
    assert all(
        visible.contains(node.sceneBoundingRect()) for node in viewer.nodes.values()
    )
    assert source.connected(destination)
    assert set(filter_node.parameter_guis) == {"highpass", "lowpass"}
    try:
        yield window
    finally:
        window.close()
        qapp.setStyle(previous_style)
        qapp.setPalette(previous_palette)
        qapp.setFont(previous_font)


@pytest.mark.parametrize(
    "scenario", ["pipeline", "node-picker", "function-importer", "coregistration"]
)
def test_documentation_screenshot(documentation_window, qtbot, tmp_path, scenario):
    """Capture ready widgets, normalize HiDPI sizes, and verify PNG round trips."""
    window = documentation_window
    if scenario == "pipeline":
        widget = window
        expected_size = QSize(1800, 900)
        assert len(window.viewer.nodes) == 8
        epochs = window.viewer.function_nodes["create_epochs"]
        average = window.viewer.function_nodes["average_epochs"]
        assert epochs.output(port_name="epochs").connected(
            average.input(port_name="epochs")
        )
        window.controller.ensure_deriv_root(interactive=False)
        window.controller.ensure_subjects_dir(interactive=False)
        window.controller.flush()
        window.viewer.start_nodes([window.viewer.input_node])
        dock = window.console_dock
        assert dock.isVisible()
        dock.setMinimumWidth(420)
        dock.setMaximumWidth(500)
        window.resizeDocks([dock], [480], Qt.Orientation.Horizontal)
        process = dock.processes[-1]
        qtbot.waitUntil(
            lambda: process.state() == QProcess.ProcessState.NotRunning, timeout=90000
        )
        console = dock.tab_widget.currentWidget().layout().itemAt(0).widget()
        assert process.exitCode() == 0, console.toPlainText()
        qtbot.waitUntil(
            lambda: "Pipeline finished." in console.toPlainText(), timeout=10000
        )
        window.viewer.ensure_visible(
            window.viewer._combined_rect(window.viewer.nodes.values())
        )
        visible = window.viewer.mapToScene(
            window.viewer.viewport().rect()
        ).boundingRect()
        assert all(
            visible.contains(node.sceneBoundingRect())
            for node in window.viewer.nodes.values()
        )
        assert dock.width() <= 500
    elif scenario == "node-picker":
        window.show_node_picker()
        widget = window.node_picker
        expected_size = QSize(900, 550)
        qtbot.addWidget(widget)
        widget.setFixedSize(expected_size)
        tree = widget.functions_view
        model = tree.model()
        matches = model.match(
            model.index(0, 0),
            Qt.ItemDataRole.DisplayRole,
            "example_filter",
            1,
            Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive,
        )
        assert len(matches) == 1
        function = matches[0]
        tree.setCurrentIndex(function)
        tree.resizeColumnToContents(0)
        tree.resizeColumnToContents(1)
    elif scenario == "function-importer":
        widget = FunctionImporter(
            file_path=Path(str(files("mne_nodes.resources") / "example_plugin.py")),
            parent=window,
        )
        qtbot.addWidget(widget)
        expected_size = QSize(1200, 650)
        widget.setFixedSize(expected_size)
        widget.show()
        assert widget.current_func == "example_filter"
        config = widget.func_config["example_filter"]
        assert set(config["inputs"]) == {"raw"}
        assert set(config["outputs"]) == {"raw"}
        assert set(config["parameters"]) == {"highpass", "lowpass"}
    else:
        widget = CoregDialog(window.controller, window)
        qtbot.addWidget(widget)
        expected_size = QSize(1000, 650)
        widget.setFixedSize(expected_size)
        info = mne.create_info(["EEG001"], 100, "eeg")
        info.set_montage(
            mne.channels.make_dig_montage(
                ch_pos={"EEG001": [0.0, 0.0, 0.09]},
                nasion=[0.0, 0.1, 0.0],
                lpa=[-0.08, 0.0, 0.0],
                rpa=[0.08, 0.0, 0.0],
                coord_frame="head",
            )
        )
        recordings = [
            CoregRecording(
                BIDSPath(
                    root=tmp_path / "bids",
                    subject="01",
                    session="01",
                    task="demo",
                    run=run,
                    datatype="eeg",
                    suffix="eeg",
                    extension=".fif",
                    check=False,
                ),
                info.copy(),
            )
            for run in ("01", "02")
        ]
        trans = tmp_path / "demo_trans.fif"
        mne.write_trans(trans, mne.transforms.Transform("head", "mri"))
        recordings[0].existing_trans = trans
        widget.mri_subject.addItems(["", "sub-01"])
        widget._discovered([CoregGroup(recordings)])
        widget.recording_list.view.setCurrentIndex(
            widget.recording_list.model.index(0, 0)
        )
        widget.show()
        assert len(widget.groups) == 1
        assert widget.recording_list.model.rowCount() == 2
        assert widget.mri_subject.currentText() == "sub-01"
        assert widget.auto_button.isEnabled()
        assert widget.manual_button.isEnabled()
        assert widget.reuse_button.isEnabled()

    qtbot.waitExposed(widget)
    qtbot.waitUntil(lambda: widget.isVisible() and widget.width() > 0)
    assert widget.size() == expected_size
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
    assert saved.size() == expected_size
