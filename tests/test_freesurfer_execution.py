"""FreeSurfer execution contracts without requiring a FreeSurfer installation."""

import json
import os
import pickle
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from mne_nodes.backend import freesurfer
from mne_nodes.backend._freesurfer_worker import PathPickler
from mne_nodes.backend.code_generation import CodeGenerator
from mne_nodes.backend.execution import build_command


@pytest.fixture
def external_plugin(ct):
    """Keep core routing tests independent of optional plugin installations."""
    plugin = ModuleType("test_external_plugin")
    plugin.PLUGIN_NAME = "external_test"
    plugin.CONFIG_PATH = {
        "recon-all": {
            "command": ["recon-all"],
            "command_args": {
                "subject": "-s",
                "all": "-all",
                "t1": "-i",
                "extra_args": None,
            },
            "uses_freesurfer": True,
            "inputs": {"subject": {"accepted_ports": ["subject"]}},
            "parameters": {},
            "outputs": {},
            "class_name": None,
            "target": "file",
        },
        "make_watershed_bem": {
            "module_name": "mne.bem",
            "uses_freesurfer": True,
            "inputs": {"subject": {"accepted_ports": ["subject"]}},
            "parameters": {"subjects_dir": {"gui": "PathGui", "default": None}},
            "outputs": {},
            "class_name": None,
            "target": "file",
        },
    }
    ct.load_plugin_module(plugin)
    return plugin


def test_stream_drains_fast_process_and_reports_failure(capsys):
    with pytest.raises(subprocess.CalledProcessError) as error:
        freesurfer.stream_subprocess(
            [
                sys.executable,
                "-c",
                "import sys; print('first'); print('last', file=sys.stderr); sys.exit(7)",
            ]
        )
    assert error.value.returncode == 7
    output = capsys.readouterr().out
    assert "first" in output and "last" in output


@pytest.mark.parametrize("command", [[], "recon-all"])
def test_invalid_command(command):
    with pytest.raises(ValueError, match="nonempty argument sequence"):
        freesurfer.run_freesurfer_subprocess(command, "subjects")


def test_wsl_argv_and_paths_are_not_shell_interpolated(monkeypatch):
    monkeypatch.setattr(freesurfer, "iswin", True)
    calls = []

    def capture(argv):
        calls.append(argv)
        return (
            "/mnt/c/subjects with spaces" if argv[-1].endswith("spaces") else argv[-1]
        )

    monkeypatch.setattr(freesurfer, "_capture", capture)
    streamed = []
    monkeypatch.setattr(freesurfer, "stream_subprocess", streamed.append)
    command = ["tool", "-i", r"C:\subjects with spaces", "$(touch SHOULD_NOT_EXIST)"]
    original = command.copy()
    runtime = freesurfer.FreeSurferRuntime("/opt/fs", None, "Ubuntu")
    freesurfer.run_freesurfer_subprocess(
        command, r"C:\subjects with spaces", runtime=runtime
    )
    assert command == original
    argv = streamed[0]
    assert argv[:4] == ["wsl.exe", "--distribution", "Ubuntu", "--exec"]
    assert argv[-4:] == [
        "tool",
        "-i",
        "/mnt/c/subjects with spaces",
        "$(touch SHOULD_NOT_EXIST)",
    ]
    assert all(call[4:7] == ["wslpath", "-a", "-u"] for call in calls)
    assert runtime.python is None  # Commands need no Linux Python.


@pytest.mark.parametrize("windows", [False, True])
def test_discovery_uses_environment_and_distro(monkeypatch, windows):
    monkeypatch.setattr(freesurfer, "iswin", windows)
    calls = []

    def capture(argv):
        calls.append(argv)
        return "setup chatter\nMNE_NODES_FS=/opt/fs\nMNE_NODES_PYTHON=/env/bin/python"

    monkeypatch.setattr(freesurfer, "_capture", capture)
    runtime = freesurfer.discover_freesurfer(distribution="Ubuntu")
    assert runtime == freesurfer.FreeSurferRuntime(
        "/opt/fs", "/env/bin/python", "Ubuntu"
    )
    assert calls[0][-2:] == ["mne-nodes", "" if windows else sys.executable]
    if windows:
        assert calls[0][:4] == ["wsl.exe", "--distribution", "Ubuntu", "--exec"]
    else:
        assert calls[0][:2] == ["bash", "-lic"]


def test_capture_surfaces_setup_errors(monkeypatch):
    monkeypatch.setattr(
        freesurfer.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 2, "", "missing FS"),
    )
    with pytest.raises(RuntimeError, match="missing FS"):
        freesurfer.discover_freesurfer()


@pytest.mark.skipif(sys.platform == "win32", reason="Native bash setup test")
def test_native_setup_isolated_and_arguments_literal(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(freesurfer, "iswin", False)
    home = tmp_path / "fake FS"
    home.mkdir()
    (home / "SetUpFreeSurfer.sh").write_text(
        "export MNE_NODES_TEST_FS=ready\nexport SUBJECTS_DIR=wrong\n"
    )
    runtime = freesurfer.FreeSurferRuntime(str(home), sys.executable)
    freesurfer.run_freesurfer_subprocess(
        [
            sys.executable,
            "-c",
            (
                "import os,sys; print(os.environ['MNE_NODES_TEST_FS']); "
                "print(os.environ['SUBJECTS_DIR']); print(sys.argv[1])"
            ),
            "$(echo INJECTION)",
        ],
        tmp_path / "subjects with spaces",
        runtime=runtime,
    )
    output = capsys.readouterr().out
    assert "ready" in output
    assert str(tmp_path / "subjects with spaces") in output
    assert "$(echo INJECTION)" in output
    assert "MNE_NODES_TEST_FS" not in os.environ


def test_python_worker_result_and_path_pickling(tmp_path, monkeypatch):
    monkeypatch.setattr(freesurfer, "iswin", False)
    monkeypatch.setattr(
        freesurfer,
        "run_freesurfer_subprocess",
        lambda command, *args, **kwargs: freesurfer.stream_subprocess(command),
    )
    runtime = freesurfer.FreeSurferRuntime("unused", sys.executable)
    result = freesurfer.run_freesurfer_function(
        json.loads, {"s": '{"value": [1, 2]}'}, tmp_path, runtime=runtime
    )
    assert result == {"value": [1, 2]}
    path_file = tmp_path / "paths.pkl"
    with path_file.open("wb") as stream:
        PathPickler(stream, lambda text: text + "-translated").dump(tmp_path)
    with path_file.open("rb") as stream:
        assert pickle.load(stream) == Path(str(tmp_path) + "-translated")


def test_python_requires_mne_interpreter(tmp_path):
    with pytest.raises(RuntimeError, match="No Python with MNE"):
        freesurfer.run_freesurfer_function(
            json.loads,
            {},
            tmp_path,
            runtime=freesurfer.FreeSurferRuntime("/opt/fs", None),
        )


def test_command_arguments():
    metadata = {
        "command": ["tool"],
        "command_args": {
            "subject": "-s",
            "enabled": "-all",
            "off": "-off",
            "optional": "-i",
            "repeated": "-v",
            "extra": None,
        },
    }
    assert build_command(
        metadata,
        {
            "subject": "a subject",
            "enabled": True,
            "off": False,
            "optional": None,
            "repeated": [1, 2],
            "extra": ["--x", "literal;value"],
        },
    ) == [
        "tool",
        "-s",
        "a subject",
        "-all",
        "-v",
        "1",
        "-v",
        "2",
        "--x",
        "literal;value",
    ]
    with pytest.raises(ValueError, match="No command argument mapping"):
        build_command(metadata, {"typo": 1})


def test_command_nodes_pipeline_and_roundtrip(qtbot, ct, monkeypatch, external_plugin):
    from mne_nodes.gui.node.function_node import CommandNode
    from mne_nodes.gui.node.node_viewer import NodeViewer

    viewer = NodeViewer(ct)
    qtbot.addWidget(viewer)
    node = viewer.add_function_node("recon-all")
    duplicate = viewer.add_function_node("recon-all")
    assert isinstance(node, CommandNode)
    assert ct.get_function_meta(duplicate.name)["command"] == ["recon-all"]
    saved = viewer.to_dict()
    viewer.from_dict(saved)
    assert all(isinstance(item, CommandNode) for item in viewer.function_nodes.values())

    bp = next(iter(ct.get("selected_inputs").get("eeg", [])), None)
    if bp is None:
        ct.set("selected_inputs", {"eeg": ["placeholder"]})
    description, _ = viewer.function_nodes["recon-all"].get_description()
    description["inputs"] = {"subject": ["Input"]}
    monkeypatch.setattr(CodeGenerator, "_build_header", lambda *args: "")
    code = CodeGenerator(ct, {"file": [description]}).code
    assert "ct.execute_external('recon-all'," in code
    assert "freesurfer.recon-all" not in code
    compile(code, "<command-pipeline>", "exec")


def test_controller_routes_commands_and_python(ct, monkeypatch, external_plugin):
    runtime = freesurfer.FreeSurferRuntime("/fs", "/python")
    monkeypatch.setattr(ct, "freesurfer_runtime", lambda: runtime)
    commands = []
    monkeypatch.setattr(
        "mne_nodes.backend.controller.run_freesurfer_subprocess",
        lambda argv, *args, **kwargs: commands.append(argv),
    )
    ct.execute_external("recon-all", subject="sample", all=True, t1=None, extra_args=[])
    assert commands == [["recon-all", "-s", "sample", "-all"]]
    calls = []
    monkeypatch.setattr(
        "mne_nodes.backend.controller.run_freesurfer_function",
        lambda function, kwargs, *args, **options: calls.append((function, kwargs)),
    )
    ct.execute_external("make_watershed_bem", subject="sample", subjects_dir="ignored")
    assert calls[0][0].__name__ == "make_watershed_bem"
    assert calls[0][1]["subjects_dir"] == ct.subjects_dir
    ct.get_function_meta("make_watershed_bem")["outputs"] = {"subject": {}}
    assert ct.execute_external("make_watershed_bem", subject="sample") == "sample"


def test_command_outputs_pass_through_only_after_success(
    ct, monkeypatch, external_plugin
):
    metadata = ct.get_function_meta("recon-all")
    metadata["uses_freesurfer"] = False
    metadata["outputs"] = {"subject": {}, "t1": {}}
    commands = []
    monkeypatch.setattr(
        "mne_nodes.backend.controller.stream_subprocess", commands.append
    )
    assert ct.execute_external("recon-all", subject="sample", t1="image.nii") == (
        "sample",
        "image.nii",
    )
    with pytest.raises(ValueError, match="outputs must name supplied arguments"):
        ct.execute_external("recon-all", subject="sample")
    assert len(commands) == 1

    def fail(argv):
        raise subprocess.CalledProcessError(1, argv)

    monkeypatch.setattr("mne_nodes.backend.controller.stream_subprocess", fail)
    with pytest.raises(subprocess.CalledProcessError):
        ct.execute_external("recon-all", subject="sample", t1="image.nii")


def test_freesurfer_flag_editor(qtbot):
    from mne_nodes.gui.function_widgets import FunctionImporter

    importer = FunctionImporter(
        code="def example(subject: str):\n    pass\n", plugin_name="freesurfer_test"
    )
    qtbot.addWidget(importer)
    importer.freesurfer_checkbox.setChecked(True)
    assert importer.func_config["example"]["uses_freesurfer"] is True
    importer.reanalyze()
    assert importer.func_config["example"]["uses_freesurfer"] is True
    importer.func_config.clear()


def test_setup_dialog_discovery(qtbot, ct, monkeypatch):
    from qtpy.QtWidgets import QLineEdit

    from mne_nodes.gui.freesurfer_widgets import FreeSurferSetupDialog

    runtime = freesurfer.FreeSurferRuntime("/opt/fs", "/env/bin/python", "Ubuntu")
    monkeypatch.setattr(ct, "freesurfer_runtime", lambda: runtime)
    dialog = FreeSurferSetupDialog(ct)
    qtbot.addWidget(dialog)
    assert dialog.findChildren(QLineEdit) == [dialog.distribution]
    assert dialog.discover_button.text() == "Discover"
    dialog.discover()
    qtbot.waitUntil(dialog.discover_button.isEnabled)
    assert "/opt/fs" in dialog.status.toPlainText()
    assert "/env/bin/python" in dialog.status.toPlainText()


@pytest.mark.skipif(
    os.environ.get("MNENODES_TEST_FREESURFER") != "1",
    reason="Opt-in integration test needs FreeSurfer, MNE and a valid license",
)
def test_real_watershed_temporary_subject(tmp_path):
    """Verify actual surfaces, not just a successful subprocess exit code."""
    import mne

    runtime = freesurfer.discover_freesurfer()
    source = f"{runtime.fs_path}/subjects/fsaverage/mri/T1.mgz"
    if freesurfer.iswin:
        source = freesurfer._capture(
            [*freesurfer._wsl_prefix(runtime.distribution), "wslpath", "-w", source]
        )
    subjects = tmp_path / "subjects with spaces"
    mri_dir = subjects / "smoke" / "mri"
    mri_dir.mkdir(parents=True)
    shutil.copy2(source, mri_dir / "T1.mgz")
    freesurfer.run_freesurfer_subprocess(
        ["mri_convert", "--version"], subjects, runtime=runtime
    )
    result = freesurfer.run_freesurfer_function(
        mne.bem.make_watershed_bem,
        {"subject": "smoke", "subjects_dir": subjects, "show": False},
        subjects,
        runtime=runtime,
    )
    assert result is None
    for surface in ("inner_skull", "outer_skull", "outer_skin"):
        output = subjects / "smoke" / "bem" / f"{surface}.surf"
        vertices, triangles = mne.read_surface(output)
        assert vertices.shape[0] > 0 and vertices.shape[1] == 3
        assert triangles.shape[0] > 0 and triangles.shape[1] == 3
