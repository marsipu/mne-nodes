"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import json
import os
import subprocess
import sys
import time
from queue import Empty, Queue
from threading import Thread

import pytest
from qtpy.QtCore import QTimer
from qtpy.QtWidgets import QWidget

from mne_nodes.backend.pipeline_utils import open_plot_windows, wait_for_plots

EVENT_ID = {
    "Auditory/Left": 1,
    "Auditory/Right": 2,
    "Visual/Left": 3,
    "Visual/Right": 4,
    "Smiley": 5,
    "Button": 32,
}

PLOT_PLUGIN_CODE = '''
import mne


def plot_raw_browser(raw):
    """Plot raw data with the Qt browser."""
    mne.viz.set_browser_backend("qt")
    raw.plot(block=False)


def make_epochs(raw):
    """Create epochs from the annotations of raw."""
    events, event_id = mne.events_from_annotations(raw)
    return mne.Epochs(raw, events, event_id, tmin=-0.1, tmax=0.3, preload=True)


def make_evokeds(epochs):
    """Average epochs."""
    return epochs.average()


def plot_evoked_figure(evokeds):
    """Plot evokeds with Matplotlib."""
    evokeds.plot(show=True)


def make_stc(evokeds, inverse_fname):
    """Apply an inverse operator to evokeds."""
    inv = mne.minimum_norm.read_inverse_operator(inverse_fname)
    return mne.minimum_norm.apply_inverse(evokeds, inv, lambda2=1 / 9)


def plot_stc_brain(stc, fs_dir):
    """Plot a source estimate with the PyVista 3D backend."""
    mne.viz.set_3d_backend("pyvistaqt")
    stc.plot(subject="sample", subjects_dir=fs_dir, hemi="lh", time_viewer=False)
'''


def _port(name):
    return {name: {"accepted_ports": [name], "optional": False}}


def _func_config(inputs, outputs=(), parameters=None):
    return {
        "inputs": {k: v for name in inputs for k, v in _port(name).items()},
        "outputs": {k: v for name in outputs for k, v in _port(name).items()},
        "parameters": parameters or {},
        "target": "file",
        "class_name": None,
    }


PLOT_PLUGIN_CONFIG = {
    "plot_raw_browser": _func_config(["raw"]),
    "make_epochs": _func_config(["raw"], ["epochs"]),
    "make_evokeds": _func_config(["epochs"], ["evokeds"]),
    "plot_evoked_figure": _func_config(["evokeds"]),
    "make_stc": _func_config(
        ["evokeds"],
        ["stc"],
        {"inverse_fname": {"default": "", "gui": "PathGui"}},
    ),
    "plot_stc_brain": _func_config(
        ["stc"], parameters={"fs_dir": {"default": "", "gui": "PathGui"}}
    ),
}


def test_wait_for_plots_blocks_until_closed(qtbot):
    """wait_for_plots returns only after all open plot windows were closed."""
    widget = QWidget()
    qtbot.addWidget(widget)
    widget.show()
    assert widget in open_plot_windows()
    QTimer.singleShot(500, widget.close)
    start = time.perf_counter()
    wait_for_plots(poll_interval=50)
    assert time.perf_counter() - start >= 0.4
    assert widget not in open_plot_windows()


@pytest.mark.parametrize("keep_plots_open", [True, False])
def test_controller_wait_for_plots_setting(ct, monkeypatch, keep_plots_open):
    """The controller only waits for plots if enabled in the settings."""
    calls = []
    monkeypatch.setattr(
        "mne_nodes.backend.controller.wait_for_plots", lambda: calls.append(True)
    )
    ct.settings.set("keep_plots_open", keep_plots_open)
    ct.wait_for_plots()
    assert calls == ([True] if keep_plots_open else [])


def test_keep_plots_open_action(main_window):
    """The settings menu toggles the device setting."""
    action = main_window.keep_plots_action
    assert action.isChecked() == main_window.settings.get("keep_plots_open")
    action.setChecked(False)
    assert main_window.settings.get("keep_plots_open") is False
    action.setChecked(True)
    assert main_window.settings.get("keep_plots_open") is True


def _write_meg_bids(bids_root):
    import mne
    from mne_bids import BIDSPath, write_raw_bids

    data_path = mne.datasets.testing.data_path()
    meg_path = data_path / "MEG" / "sample"
    raw = mne.io.read_raw_fif(meg_path / "sample_audvis_trunc_raw.fif")
    raw.info["line_freq"] = 60
    events = mne.read_events(meg_path / "sample_audvis_trunc_raw-eve.fif")
    events = events[events[:, 2] != 0]
    bids_path = BIDSPath(
        subject="01",
        session="01",
        task="audiovisual",
        run="1",
        datatype="meg",
        root=bids_root,
    )
    write_raw_bids(
        raw, bids_path, events=events, event_id=EVENT_ID, overwrite=True, verbose=0
    )
    return data_path, bids_path


def _read_lines(stream, queue):
    for line in iter(stream.readline, ""):
        queue.put(line)
    stream.close()


def _wait_for_line(queue, text, timeout, output, process):
    end = time.perf_counter() + timeout
    while time.perf_counter() < end:
        try:
            line = queue.get(timeout=0.5)
        except Empty:
            if process.poll() is not None:
                break
            continue
        output.append(line)
        if text in line:
            return line
    raise AssertionError(f"'{text}' not found in output:\n{''.join(output)}")


@pytest.mark.timeout(600)
@pytest.mark.parametrize("keep_plots_open", [True, False])
def test_pipeline_plots_stay_open(
    qtbot, tmp_path, monkeypatch, settings, keep_plots_open
):
    """Plots of a raw->epochs->evokeds->stc pipeline stay open if enabled."""
    pytest.importorskip("mne_qt_browser")
    pytest.importorskip("pyvistaqt")
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
        pytest.skip("Requires a display to open plot windows.")
    from mne_nodes.backend.code_generation import CodeGenerator
    from mne_nodes.gui.node.node_viewer import NodeViewer
    from mne_nodes.gui.widget_registry import widget_registry
    from tests.conftest import create_test_controller

    ct = create_test_controller(
        settings=settings, tmp_path=tmp_path, monkeypatch=monkeypatch
    )
    # Replace the tiny EEG dataset with the MEG testing dataset
    data_path, bids_path = _write_meg_bids(tmp_path / "meg_bids")
    settings.set("bids_root", tmp_path / "meg_bids")
    settings.set("keep_plots_open", keep_plots_open)

    plugin_dir = tmp_path / "plot_pipeline"
    plugin_dir.mkdir()
    (plugin_dir / "plot_pipeline.py").write_text(PLOT_PLUGIN_CODE, encoding="utf-8")
    config_path = plugin_dir / "plot_pipeline_config.json"
    config_path.write_text(json.dumps(PLOT_PLUGIN_CONFIG), encoding="utf-8")
    ct.load_plugin_path(config_path)
    meg_path = data_path / "MEG" / "sample"
    ct.set_parameter(
        "inverse_fname",
        meg_path / "sample_audvis_trunc-meg-eeg-oct-6-meg-inv.fif",
        "make_stc",
    )
    ct.set_parameter("fs_dir", data_path / "subjects", "plot_stc_brain")
    ct.set("selected_inputs", {"meg": [bids_path.fpath.name]})
    ct.flush()

    viewer = NodeViewer(ct)
    qtbot.addWidget(viewer)
    in_node = viewer.add_input_node()
    nodes = {
        name: viewer.add_function_node(name)
        for name in (
            "plot_raw_browser",
            "make_epochs",
            "make_evokeds",
            "plot_evoked_figure",
            "make_stc",
            "plot_stc_brain",
        )
    }
    meg_out = in_node.output(port_name="meg")
    meg_out.connect_to(nodes["plot_raw_browser"].input(port_name="raw"))
    meg_out.connect_to(nodes["make_epochs"].input(port_name="raw"))
    for source, port, target in (
        ("make_epochs", "epochs", "make_evokeds"),
        ("make_evokeds", "evokeds", "plot_evoked_figure"),
        ("make_evokeds", "evokeds", "make_stc"),
        ("make_stc", "stc", "plot_stc_brain"),
    ):
        nodes[source].output(port_name=port).connect_to(
            nodes[target].input(port_name=port)
        )
    node_sequence = viewer.get_node_sequence(viewer.input_node)
    for sequence in node_sequence.values():
        for node in sequence:
            node["checked"] = False

    script_path = tmp_path / "plot_pipeline_run.py"
    script_path.write_text(CodeGenerator(ct, node_sequence).code, encoding="utf-8")
    # Avoid leaking the viewer into later tests through the widget registry
    widget_registry().unregister("viewer", viewer)

    env = os.environ.copy()
    env.pop("MPLBACKEND", None)
    env.pop("PYTEST_CURRENT_TEST", None)
    env["PYTHONUNBUFFERED"] = "1"
    process = subprocess.Popen(
        [sys.executable, str(script_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        cwd=tmp_path,
    )
    queue = Queue()
    Thread(target=_read_lines, args=(process.stdout, queue), daemon=True).start()
    output = []
    try:
        _wait_for_line(queue, "Pipeline finished.", 300, output, process)
        if keep_plots_open:
            line = _wait_for_line(
                queue, "plot window(s) to be closed", 60, output, process
            )
            # Raw browser (Qt), evoked figure (Matplotlib) and brain (PyVista)
            assert int(line.split("Waiting for ")[1].split()[0]) >= 3
            time.sleep(3)
            assert process.poll() is None, "Plots were closed with the process."
        else:
            assert process.wait(timeout=60) == 0, "".join(output)
            while not queue.empty():
                output.append(queue.get())
            assert "to be closed" not in "".join(output)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=30)
