"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import mne
import pytest

from mne_nodes.backend.controller import Controller
from mne_nodes.backend.io import TypedJSONEncoder
from mne_nodes.backend.pipeline_utils import change_file_section


def test_datatype_items(ct, monkeypatch):
    class FakeBIDSPath:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def match(self, ignore_json):
            if self.kwargs.get("suffix") == "eeg":
                return [recording]
            if self.kwargs.get("suffix") == "meg":
                return [empty_room]
            return []

    class FakeCandidate:
        def __init__(self, basename, empty_room=None):
            self.basename = basename
            self.acquisition = None
            self.empty_room = empty_room
            self.datatype = "meg" if "meg" in basename else "eeg"
            self.subject = "emptyroom" if "emptyroom" in basename else "01"
            self.task = "noise" if "emptyroom" in basename else "test"

        def find_empty_room(self):
            return self.empty_room

    empty_room = FakeCandidate("sub-emptyroom_task-noise_meg.fif")
    recording = FakeCandidate("sub-01_task-test_eeg.vhdr", empty_room)
    bids_path_calls = []

    def fake_bids_path(**kwargs):
        bids_path_calls.append(kwargs)
        return FakeBIDSPath(**kwargs)

    monkeypatch.setattr("mne_nodes.backend.controller.BIDSPath", fake_bids_path)

    assert ct.get_datatype_items("event_id") == []
    assert ct.get_datatype_items("info") == []
    assert ct.get_datatype_items("trans") == []
    assert ct.get_datatype_items("eeg") == ["sub-01_task-test_eeg.vhdr"]
    assert bids_path_calls == [{"root": ct.bids_root, "check": False, "suffix": "eeg"}]

    assert ct.get_datatype_items("emptyroom") == ["sub-emptyroom_task-noise_meg.fif"]
    assert [call["suffix"] for call in bids_path_calls[1:]] == ["meg"]

    # Additional metadata types use the same output-only handling.
    ct.non_selectable_datatypes.append("metadata")
    monkeypatch.setattr(
        "mne_nodes.backend.controller.get_datatypes", lambda root: ["eeg"]
    )
    assert ct.get_datatypes() == [
        "eeg",
        "event_id",
        "info",
        "trans",
        "raw_er",
        "anat",
        "metadata",
        "subject",
    ]
    assert ct.get_datatype_items("metadata") == []
    assert ct.get_datatype_items("anat") == []
    assert not set(ct.non_selectable_datatypes) & ct.get_all_datatype_items().keys()


@pytest.mark.parametrize("grouped", [False, True])
def test_load_recording_metadata(ct, grouped):
    """Load info, shared transformations and MRI associations for selected data."""
    import mne
    from mne_bids import get_bids_path_from_fname

    from mne_nodes.backend.coregistration import trans_path

    path = get_bids_path_from_fname(next(ct.bids_root.rglob("*_eeg.vhdr")))
    items = [path] if grouped else path
    raw, _ = ct.load_raw(items)
    info = ct.load_info(items)
    if grouped:
        raw, info = raw[0], info[0]
    assert info["ch_names"] == raw.info["ch_names"]
    assert info["sfreq"] == raw.info["sfreq"]
    assert info["dig"] == raw.info["dig"]

    root = ct.ensure_deriv_root(False)
    with pytest.raises(FileNotFoundError, match="No transformation"):
        ct.load_trans(items)
    with pytest.raises(FileNotFoundError, match="No matching FreeSurfer"):
        ct.load_recording_subject(items)
    subject = "individual-mri"
    for folder in ("mri", "surf", "label"):
        (ct.ensure_subjects_dir(False) / subject / folder).mkdir(parents=True)
    ct.set("coreg_subjects", {path.basename: subject})
    assert ct.load_recording_subject(items) == subject
    destination = trans_path(path.copy().update(task=None, run=None), root)
    destination.parent.mkdir(parents=True)
    mne.write_trans(destination, mne.transforms.Transform("head", "mri"))
    trans = ct.load_trans(items)
    if grouped:
        trans = trans[0]
    assert isinstance(trans, mne.transforms.Transform)
    assert trans["from"] == mne.io.constants.FIFF.FIFFV_COORD_HEAD
    assert trans["to"] == mne.io.constants.FIFF.FIFFV_COORD_MRI


def test_recording_anat_resolution_and_codegen_cache(ct, monkeypatch):
    """Use one matched T1w per recording and reuse anat-only work per subject."""
    from types import SimpleNamespace
    from unittest.mock import Mock

    from mne_bids import get_bids_path_from_fname

    from mne_nodes.backend.code_generation import CodeGenerator

    recording = get_bids_path_from_fname(next(ct.bids_root.rglob("*_eeg.vhdr")))
    second = recording.copy().update(task="other", run="99")
    second.fpath.touch()
    subject_anat = recording.copy().update(
        datatype="anat",
        session=None,
        task=None,
        run=None,
        suffix="T1w",
        extension=".nii.gz",
    )
    subject_anat.directory.mkdir(parents=True, exist_ok=True)
    subject_anat.fpath.touch()
    if recording.session is not None:
        recording_anat = subject_anat.copy().update(session=recording.session)
        recording_anat.directory.mkdir(parents=True, exist_ok=True)
        recording_anat.fpath.touch()
        assert ct.find_recording_anat(recording) == recording_anat
    else:
        recording_anat = subject_anat
    assert ct.load_anat(recording) == recording_anat.fpath

    ambiguous = recording_anat.copy().update(acquisition="highres")
    ambiguous.directory.mkdir(parents=True, exist_ok=True)
    ambiguous.fpath.touch()
    with pytest.raises(ValueError, match="Ambiguous T1w anatomy"):
        ct.find_recording_anat(recording)
    ambiguous.fpath.unlink()

    metadata = {
        "inputs": {"mri": {"accepted_ports": ["anat"], "optional": False}},
        "parameters": {},
        "outputs": {"model": {"accepted_ports": ["model"]}},
        "class_name": None,
        "plugin": "anatomy_plugin",
    }
    ct.function_meta["build_anat_model"] = metadata
    ct.set(
        "selected_inputs",
        {"eeg": [recording.basename, second.basename], "anat": ["ignored.nii.gz"]},
    )
    monkeypatch.setattr(CodeGenerator, "_build_header", lambda *args: "")
    build_model = Mock(return_value="model")
    code = CodeGenerator(
        ct,
        {
            "file": [
                {
                    "name": "build_anat_model",
                    "function_meta": metadata,
                    "inputs": {"mri": ["Input-0"]},
                    "input_ports": {"mri": ["anat"]},
                    "outputs": {"model": ["model"]},
                    "checked": False,
                }
            ]
        },
    ).code
    assert "# Selection-Type: anat" not in code
    exec(  # noqa: S102 - Validate generated pipeline execution.
        compile(code, "<anatomy pipeline>", "exec"),
        {
            "ct": ct,
            "get_bids_path_from_fname": get_bids_path_from_fname,
            "anatomy_plugin": SimpleNamespace(build_anat_model=build_model),
        },
    )
    build_model.assert_called_once_with(mri=recording_anat.fpath)


def test_trans_lookup_availability(ct):
    """Availability and loading use the same lookup, incl. legacy and ambiguity."""
    import mne
    from mne_bids import get_bids_path_from_fname

    from mne_nodes.backend.coregistration import trans_path

    path = get_bids_path_from_fname(next(ct.bids_root.rglob("*_eeg.vhdr")))
    ct.set("selected_inputs", {"eeg": [path.basename]})
    assert "trans" in ct.input_output_availability()
    name = path.copy().update(suffix=None, extension=None, check=False).basename
    legacy = (
        ct.bids_root
        / "derivatives"
        / "mne-pipeline-hd"
        / f"sub-{path.subject}"
        / f"{name}-trans.fif"
    )
    if path.session is not None:
        legacy = legacy.parent / f"ses-{path.session}" / legacy.name
    legacy.parent.mkdir(parents=True)
    mne.write_trans(legacy, mne.transforms.Transform("head", "mri"))
    assert ct.find_recording_trans(path) == legacy
    assert "trans" not in ct.input_output_availability()
    assert isinstance(ct.load_trans(path), mne.transforms.Transform)

    path = path.copy().update(run="99")
    path.fpath.touch()
    root = ct.ensure_deriv_root(False)
    for task in (None, path.task):
        candidate = trans_path(path.copy().update(task=task, run=None), root)
        candidate.parent.mkdir(parents=True, exist_ok=True)
        mne.write_trans(candidate, mne.transforms.Transform("head", "mri"))
    ct.set("selected_inputs", {"eeg": [path.basename]})
    assert "Ambiguous" in ct.input_output_availability()["trans"]
    with pytest.raises(ValueError, match="Ambiguous"):
        ct.load_trans(path)


@pytest.mark.parametrize("scope", ["subject", "custom"])
def test_selected_group_recordings_and_output_availability(ct, scope):
    """Recording groups use real raw members, excluding BrainVision companions."""
    import mne
    from mne_bids import get_bids_path_from_fname

    from mne_nodes.backend.coregistration import trans_path

    source = next(ct.bids_root.rglob("*_eeg.vhdr"))
    path = get_bids_path_from_fname(source)
    name = path.subject if scope == "subject" else "my-group"
    if scope == "custom":
        ct.set("custom_groups", {name: [str(source)]})
    ct.set("selected_inputs", {scope: [name]})
    assert ct.selected_recordings() == [path]
    assert "trans" in ct.input_output_availability()
    assert "subject" in ct.input_output_availability()
    for folder in ("mri", "surf", "label"):
        (ct.ensure_subjects_dir(False) / f"sub-{path.subject}" / folder).mkdir(
            parents=True
        )
    destination = trans_path(path, ct.ensure_deriv_root(False))
    destination.parent.mkdir(parents=True)
    mne.write_trans(destination, mne.transforms.Transform("head", "mri"))
    available = ct.input_output_availability()
    assert "trans" not in available
    assert "subject" not in available
    assert "info" not in available


def test_discard_segmentation_checks_preserves_subject_groups(ct):
    """Old segmentation checks are removed without losing recording groups."""
    from mne_bids import get_bids_path_from_fname

    recording = get_bids_path_from_fname(next(ct.bids_root.rglob("*_eeg.vhdr")))
    subject = f"sub-{recording.subject}"
    for folder in ("mri", "surf", "label"):
        (ct.ensure_subjects_dir(False) / subject / folder).mkdir(parents=True)
    ct.set("selected_inputs", {"subject": [recording.subject, subject]})
    ct.discard_legacy_segmentation_checks()
    assert ct.get("selected_inputs") == {"subject": [recording.subject]}
    assert ct.selected_recordings() == [recording]
    assert "subject" not in ct.input_output_availability()
    ct.discard_legacy_segmentation_checks()
    assert ct.get("selected_inputs") == {"subject": [recording.subject]}


@pytest.mark.parametrize("target", ["file", "group"])
@pytest.mark.parametrize("mutate_before_solve", [False, True])
def test_codegen_reuses_subject_derivatives_within_run(
    ct, monkeypatch, target, mutate_before_solve
):
    """Share MRI-only chains, but keep recording results and node parameters apart."""
    from types import SimpleNamespace
    from unittest.mock import Mock

    from mne_bids import get_bids_path_from_fname

    from mne_nodes.backend.code_generation import CodeGenerator

    first = get_bids_path_from_fname(next(ct.bids_root.rglob("*_eeg.vhdr")))
    second = first.copy().update(subject="02", run="98")
    third = first.copy().update(subject="99", run="99")
    for path in (second, third):
        path.directory.mkdir(parents=True, exist_ok=True)
        path.fpath.touch()
    paths = [first, second, third]
    mri_subjects = ["shared-mri", "shared-mri", "other-mri"]
    for subject in set(mri_subjects):
        for folder in ("mri", "surf", "label"):
            (ct.ensure_subjects_dir(False) / subject / folder).mkdir(parents=True)
    ct.set(
        "coreg_subjects",
        dict(zip([path.basename for path in paths], mri_subjects, strict=True)),
    )
    if target == "file":
        ct.set("selected_inputs", {"eeg": [path.basename for path in paths]})
    else:
        groups = {f"group{index}": [path] for index, path in enumerate(paths)}
        ct.set("selected_inputs", {"custom": list(groups)})
        monkeypatch.setattr(ct, "get_group_by", lambda scope: groups)

    def node(name, inputs, outputs):
        metadata = {
            "inputs": {
                key: {"accepted_ports": aliases} for key, aliases in inputs.items()
            },
            "parameters": {},
            "outputs": {key: {} for key in outputs},
            "class_name": None,
            "plugin": "subject_plugin",
        }
        ct.function_meta[name] = metadata
        return {
            "name": name,
            "function_meta": metadata,
            "inputs": {key: ["input"] for key in inputs},
            "outputs": {key: [] for key in outputs},
            "checked": False,
        }

    nodes = [
        node("make_model", {"subject": ["subject"]}, ["surfaces", "surface_alias"]),
        node("solve_model", {"surfs": ["surfaces"]}, ["bem"]),
        node("observe_alias", {"surface_alias": ["surface_alias"]}, []),
        node("make_forward", {"bem": ["bem"], "info": ["info"]}, ["forward"]),
        node("make_model-1", {"subject": ["subject"]}, ["surfaces", "surface_alias"]),
    ]
    if mutate_before_solve:
        nodes.insert(
            1, node("modify_surfaces", {"surfaces": ["surfaces"], "info": ["info"]}, [])
        )
    monkeypatch.setattr(
        ct,
        "func_parameters",
        lambda name: (
            {"ico": 5 if name.endswith("-1") else 4}
            if name.startswith("make_model")
            else {}
        ),
    )
    monkeypatch.setattr(ct, "load_info", lambda items, raw=None: items)

    def model(subject, ico):
        surfaces = [subject, ico]
        return surfaces, surfaces

    def solve(surfs):
        surfs.append("solved")
        return {"surfaces": list(surfs)}

    make_model = Mock(side_effect=model)
    solve_model = Mock(side_effect=solve)
    aliases = []
    seen = []

    def make_forward(bem, info):
        seen.append((bem["surfaces"].copy(), info))
        bem["surfaces"].append("recording-specific mutation")
        return "forward"

    forward = Mock(side_effect=make_forward)
    plugin = SimpleNamespace(
        make_model=make_model,
        solve_model=solve_model,
        make_forward=forward,
        modify_surfaces=lambda surfaces, info: surfaces.append("recording-dependent"),
        observe_alias=lambda surface_alias: aliases.append(surface_alias.copy()),
    )
    monkeypatch.setattr(CodeGenerator, "_build_header", lambda *args: "")
    code = CodeGenerator(ct, {target: nodes}).code

    def run():
        exec(  # noqa: S102 - Validate generated pipeline execution.
            compile(code, "<subject pipeline>", "exec"),
            {
                "ct": ct,
                "get_bids_path_from_fname": get_bids_path_from_fname,
                "subject_plugin": plugin,
            },
        )

    run()
    assert make_model.call_count == 4  # Two subjects, two independent nodes.
    assert solve_model.call_count == (3 if mutate_before_solve else 2)
    assert forward.call_count == 3
    extra = ["recording-dependent", "solved"] if mutate_before_solve else ["solved"]
    assert [item[0] for item in seen] == [
        ["shared-mri", 4, *extra],
        ["shared-mri", 4, *extra],
        ["other-mri", 4, *extra],
    ]
    assert [
        item[1].basename if target == "file" else item[1][0].basename for item in seen
    ] == [path.basename for path in paths]
    assert aliases == [item[0] for item in seen]
    assert sorted(call.kwargs["ico"] for call in make_model.call_args_list) == [
        4,
        4,
        5,
        5,
    ]
    run()
    assert make_model.call_count == 8
    assert solve_model.call_count == (6 if mutate_before_solve else 4)
    assert forward.call_count == 6


@pytest.mark.parametrize("target", ["file", "group"])
@pytest.mark.parametrize(
    "inputs",
    [
        ["event_id"],
        ["info"],
        ["raw", "event_id", "info"],
        ["event_id", "raw", "info"],
        ["trans", "subject"],
    ],
)
def test_codegen_bids_metadata_inputs(ct, monkeypatch, target, inputs):
    """Load metadata ports independently and reuse raw within the same node."""
    from types import SimpleNamespace
    from unittest.mock import Mock

    from mne_bids import get_bids_path_from_fname

    from mne_nodes.backend.code_generation import CodeGenerator

    source = next(ct.bids_root.rglob("*_eeg.vhdr"))
    path = get_bids_path_from_fname(source)
    if "trans" in inputs:
        import mne

        from mne_nodes.backend.coregistration import trans_path

        destination = trans_path(path, ct.ensure_deriv_root(False))
        destination.parent.mkdir(parents=True)
        mne.write_trans(destination, mne.transforms.Transform("head", "mri"))
        for folder in ("mri", "surf", "label"):
            (ct.ensure_subjects_dir(False) / f"sub-{path.subject}" / folder).mkdir(
                parents=True
            )
    if target == "file":
        ct.set("selected_inputs", {"eeg": [source.name]})
    else:
        ct.set("selected_inputs", {"subject": [path.subject]})
        monkeypatch.setattr(ct, "get_group_by", lambda scope: {path.subject: [path]})
    metadata = {
        "inputs": {name: {"accepted_ports": [name]} for name in inputs},
        "parameters": {},
        "outputs": {},
        "class_name": None,
        "plugin": "metadata_plugin",
    }
    ct.function_meta["consume_metadata"] = metadata
    consumer = Mock()
    load_raw = Mock(wraps=ct.load_raw)
    monkeypatch.setattr(ct, "load_raw", load_raw)
    monkeypatch.setattr(CodeGenerator, "_build_header", lambda *args: "")
    nodes = {
        target: [
            {
                "name": "consume_metadata",
                "function_meta": metadata,
                "inputs": {name: ["input"] for name in inputs},
                "outputs": {},
                "checked": False,
            }
        ]
    }
    code = CodeGenerator(ct, nodes).code
    exec(  # noqa: S102 - Validate generated pipeline execution.
        compile(code, "<metadata pipeline>", "exec"),
        {
            "ct": ct,
            "get_bids_path_from_fname": get_bids_path_from_fname,
            "metadata_plugin": SimpleNamespace(consume_metadata=consumer),
        },
    )
    consumer.assert_called_once()
    values = consumer.call_args.kwargs
    assert set(values) == set(inputs)
    assert load_raw.call_count == int("raw" in inputs or "event_id" in inputs)
    if "trans" in inputs:
        trans = values["trans"][0] if target == "group" else values["trans"]
        assert isinstance(trans, mne.transforms.Transform)
        assert values["subject"] == f"sub-{path.subject}"
    if "event_id" in inputs:
        event_id = values["event_id"]
        if target == "group":
            event_id = event_id[0]
        assert isinstance(event_id, dict)
        assert event_id
    if "info" in inputs:
        info = values["info"]
        if target == "group":
            info = info[0]
        assert info["ch_names"]
        if "raw" in inputs:
            raw = values["raw"][0] if target == "group" else values["raw"]
            assert info is raw.info


@pytest.mark.parametrize("port", ["eeg", "raw_er"])
@pytest.mark.parametrize("from_dataset", [True, False])
def test_codegen_raw_method_uses_connected_receiver(
    ct, monkeypatch, port, from_dataset
):
    """Raw method receivers use live upstream values or direct dataset loaders."""
    from types import SimpleNamespace

    from mne_bids import get_bids_path_from_fname

    from mne_nodes.backend.code_generation import CodeGenerator

    recording_path = next(ct.bids_root.rglob("*_eeg.vhdr"))
    ct.set("selected_inputs", {"eeg": [recording_path.name]})
    method_meta = {
        "inputs": {"raw": {"accepted_ports": [port]}},
        "outputs": {},
        "parameters": {},
        "class_name": "Raw",
    }
    ct.function_meta["Raw.filter"] = method_meta
    nodes = []
    source = "Input-0"
    if not from_dataset:
        plugin_name = "receiver_plugin"
        function_name = "make_recording"
        output_meta = {
            "inputs": {},
            "outputs": {port: {}},
            "parameters": {},
            "class_name": None,
            "plugin": plugin_name,
        }
        ct.function_meta[function_name] = output_meta
        nodes.append(
            {
                "name": function_name,
                "function_meta": output_meta,
                "inputs": {},
                "outputs": {port: []},
                "checked": False,
            }
        )
        source = function_name
    nodes.append(
        {
            "name": "Raw.filter",
            "function_meta": method_meta,
            "inputs": {"raw": [source]},
            "input_ports": {"raw": [port]},
            "outputs": {},
            "checked": False,
        }
    )
    monkeypatch.setattr(CodeGenerator, "_build_header", lambda *args: "")
    monkeypatch.setattr(ct, "func_parameters", lambda _name: {})

    class Recording:
        def __init__(self):
            self.filter_calls = 0

        def filter(self, **_kwargs):
            self.filter_calls += 1

    code = CodeGenerator(ct, {"file": nodes}).code
    recording = Recording()

    receiver = "_recording_raw" if port == "eeg" else "raw_er"
    if from_dataset:
        assert f"{receiver}.filter(" in code
        assert (
            "ct.load_raw(bp)" in code if port == "eeg" else "ct.load_raw_er(bp)" in code
        )
        if port == "eeg":
            monkeypatch.setattr(ct, "load_raw", lambda _bp: (recording, {}))
        else:
            monkeypatch.setattr(ct, "load_raw_er", lambda _bp: recording)
    else:
        assert f"{port}.filter(" in code
        assert "ct.load_raw(" not in code
        assert "ct.load_raw_er(" not in code
    namespace = {"ct": ct, "get_bids_path_from_fname": get_bids_path_from_fname}
    if not from_dataset:
        namespace["receiver_plugin"] = SimpleNamespace(
            make_recording=lambda **_kwargs: recording
        )
    exec(compile(code, "<generated raw method>", "exec"), namespace)  # noqa: S102
    assert recording.filter_calls == 1


def test_plugin_import_reload_and_remove(ct, test_plugin_config, test_script):
    assert "validation_functions" in ct.plugins

    ct.load_plugin_path(test_plugin_config)
    assert "test_module" in ct.plugins, "Custom plugin should be imported"
    assert ct.get_plugin_from_function("test_func1") == "test_module"
    assert ct.get("plugin_meta")["test_module"] == {
        "config_path": test_plugin_config,
        "script_path": test_script,
        "plugin_type": "path",
    }
    assert ct.plugins["test_module"].test_func1(2) == 4

    # Modify the module source code and reload
    _func1_code, start, end = ct.get_function_code("test_func1")
    new_test_code = "def test_func1(a):\n    return a ** 3\n"
    change_file_section(test_script, (start, end), new_test_code)
    ct.reload_plugins()
    assert ct.plugins["test_module"].test_func1(2) == 8

    # Removing unregisters the plugin without deleting its files
    ct.settings.set("disabled_plugins", ["test_module"])
    ct.remove_plugin("test_module")
    assert test_plugin_config.is_file()
    assert test_script.is_file()
    assert "test_module" not in ct.plugins
    assert "test_module" not in ct.get("plugin_meta")
    assert "test_module" not in ct.settings.get("plugin_config", {})
    assert "test_module" not in ct.settings.get("disabled_plugins", [])


def test_config_persistence_and_switch(tmp_path, ct, monkeypatch):
    ct.name = "renamed"
    ct.set_parameter("param1", 42, "test_func1")
    ct.flush()
    reloaded = Controller(config_path=ct.config_path)
    assert reloaded.name == "renamed"
    assert reloaded.parameter("param1", "test_func1") == 42
    ct.name = "test"
    ct.flush()

    old_config_path = ct.config_path
    # Check controller change with other options
    new_config_path = tmp_path / "new_config.json"
    test_dict = {
        "name": "test2",
        "parameters": {"test_func1": {"param_a": 1, "param_b": 2}},
    }
    with open(new_config_path, "w") as f:
        json.dump(test_dict, f, indent=4, cls=TypedJSONEncoder)
    # Simulate input to new config-path
    # Create a new config-file? Use existing!
    monkeypatch.setattr(
        "mne_nodes.backend.controller.ask_user_custom", lambda *a, **k: False
    )
    # Path to existing config-file
    monkeypatch.setattr(
        "mne_nodes.backend.controller.get_user_input", lambda *a, **k: new_config_path
    )
    ct.config_path = None
    assert ct.name == "test2", "Controller name should be updated to 'test2'"
    assert ct.parameter("param_a", "test_func1") == 1, (
        "New parameter should be loaded from config"
    )
    # Add parameters for test
    ct.set_parameter("new_param", 42, "test_func1")
    assert ct.parameter("new_param", "test_func1") == 42, "New parameter should be set"
    ct.flush()
    # Change back to other controller
    ct.config_path = old_config_path
    assert ct.name == "test", "Controller name should be reverted to 'test'"
    assert "new_param" not in ct.get("parameters"), (
        "Parameters should be reverted on config change"
    )
    # Change again to new config
    ct.config_path = new_config_path
    assert ct.name == "test2", "Controller name should be updated to 'test2'"
    assert ct.parameter("param_b", "test_func1") == 2, "New parameter should be set"
    assert ct.parameter("new_param", "test_func1") == 42, (
        "New parameter should persist after config reload"
    )


def test_fresh_controller_prompts(settings, tmp_path, monkeypatch):
    """Without a config nothing is resolved silently; prompts create folders."""
    controller = Controller(settings=settings)
    assert controller.config_path is None
    assert controller.bids_root is None
    assert controller.deriv_root is None
    assert controller.plot_root is None
    assert controller.name is None
    with pytest.raises(RuntimeError):
        controller.ensure_ready(required=("config_path",), interactive=False)

    bids_root = tmp_path / "bids"
    bids_root.mkdir()
    inputs = iter([bids_root, tmp_path, "demo_pipeline"])
    monkeypatch.setattr(
        "mne_nodes.backend.controller.get_user_input",
        lambda *args, **kwargs: next(inputs),
    )
    monkeypatch.setattr("mne_nodes.backend.controller.ask_user", lambda *a, **k: True)
    controller.set("name", "test")
    controller.bids_root = None
    controller.deriv_root = None
    controller.plot_root = None
    subjects_dir = controller.ensure_subjects_dir()
    assert controller.bids_root == bids_root
    assert controller.deriv_root == bids_root / "derivatives" / "mne-nodes"
    assert controller.plot_root is None
    assert subjects_dir == bids_root / "derivatives" / "freesurfer"

    saved_path = Controller(settings=settings).new_config()
    assert saved_path == tmp_path / "demo_pipeline_pipeline.json"
    assert saved_path.exists()


@pytest.mark.parametrize("action", ["load", "new", "save_as"])
def test_config_switch_confirms_bids_and_resets_outputs(
    ct, tmp_path, monkeypatch, action
):
    dataset_name = ct.get_dataset_name()
    root = ct.bids_root
    ct.ensure_deriv_root()
    ct.plot_root = tmp_path
    new_config = tmp_path / "other_pipeline.json"
    new_config.write_text(
        json.dumps(
            {
                "name": "other",
                "bids_dataset_name": dataset_name,
                "selected_inputs": {"subject": ["01"]},
                "custom_groups": {"group": ["01"]},
            }
        ),
        encoding="utf-8",
    )
    confirmations = []
    monkeypatch.setattr(
        "mne_nodes.backend.controller.ask_user",
        lambda message, **kwargs: confirmations.append(message) or True,
    )
    actions = {
        "load": ct.load_config,
        "new": ct.new_config,
        "save_as": ct.save_config_as,
    }
    actions[action](new_config)

    assert len(confirmations) == 1
    assert str(root) in confirmations[0]
    assert ct.bids_root == root
    assert ct.deriv_root == root / "derivatives" / "mne-nodes"
    assert ct.plot_root is None
    if action == "load":
        assert ct.get("selected_inputs") == {"subject": ["01"]}
        assert ct.get("custom_groups") == {"group": ["01"]}
    ct.load()
    ct.config_path = new_config
    assert len(confirmations) == 1


def test_startup_config_switch_defers_confirmation(ct, tmp_path, monkeypatch):
    ct.ensure_deriv_root()
    ct.plot_root = tmp_path
    config_path = tmp_path / "startup_pipeline.json"
    config_path.write_text(json.dumps({"name": "startup"}), encoding="utf-8")
    confirmations = []
    monkeypatch.setattr(
        "mne_nodes.backend.controller.ask_user",
        lambda message, **kwargs: confirmations.append(message) or True,
    )
    controller = Controller(config_path=config_path, settings=ct.settings)

    assert confirmations == []
    assert controller.deriv_root == ct.bids_root / "derivatives" / "mne-nodes"
    assert controller.plot_root is None
    with pytest.raises(RuntimeError, match="must be confirmed"):
        controller.ensure_bids_root(interactive=False)
    assert controller.ensure_bids_root() == ct.bids_root
    controller.ensure_bids_root()
    assert len(confirmations) == 1


@pytest.mark.parametrize("trigger", ["reselect", "config", "root"])
def test_dataset_mismatch_clears_dataset_selections(ct, tmp_path, monkeypatch, trigger):
    """A different BIDS dataset never keeps dataset-local selections."""
    old_name = ct.get_dataset_name()
    old_root = ct.bids_root
    for folder in ("mri", "surf", "label"):
        (ct.ensure_subjects_dir() / "old-subject" / folder).mkdir(parents=True)
    ct.set("selected_inputs", {"subject": ["old-subject"], "eeg": ["old_file.vhdr"]})
    ct.set("custom_groups", {"old-group": ["old_file.vhdr"]})
    ct.flush()
    new_root = tmp_path / "new_bids"
    new_root.mkdir()
    (new_root / "dataset_description.json").write_text(
        json.dumps({"Name": "New dataset"}), encoding="utf-8"
    )
    new_config = tmp_path / "other_pipeline.json"
    new_config.write_text(
        json.dumps(
            {
                "name": "other",
                "bids_dataset_name": (
                    old_name if trigger == "reselect" else "different dataset"
                ),
                "selected_inputs": {"subject": ["01"]},
                "custom_groups": {"group": ["01"]},
            }
        ),
        encoding="utf-8",
    )
    confirmations = []
    warnings = []
    monkeypatch.setattr(
        "mne_nodes.backend.controller.ask_user",
        lambda message, **kwargs: (
            confirmations.append(message) or trigger != "reselect"
        ),
    )
    monkeypatch.setattr(
        "mne_nodes.backend.controller.get_user_input", lambda *args, **kwargs: new_root
    )
    monkeypatch.setattr(
        "mne_nodes.backend.controller.raise_user_attention",
        lambda message: warnings.append(message),
    )

    if trigger == "root":
        ct.settings.set("bids_root", new_root)
        ct.load()
    else:
        ct.load_config(new_config)

    assert len(confirmations if trigger == "reselect" else warnings) == 1
    assert ct.get("selected_inputs") == {}
    assert ct.get("custom_groups") == {}
    if trigger == "config":
        assert ct.bids_root == old_root
        assert "different dataset" in warnings[0]
        assert ct.get("bids_dataset_name") == old_name
    else:
        assert ct.bids_root == new_root
        assert ct.get("bids_dataset_name") == "New dataset"
    if trigger == "root":
        assert old_name in warnings[0]
        assert "New dataset" in warnings[0]
        assert ct.subjects_dir is None
        assert ct.get_datatype_items("subject") == []
    ct.flush()
    ct.load()
    ct.settings.remove("bids_root")
    assert ct.get_dataset_name() == ct.get("bids_dataset_name")


def test_output_roots_and_optional_plots(ct, tmp_path, monkeypatch):
    """Derivatives default to the dataset; plots stay optional without prompts."""
    monkeypatch.setattr(
        "mne_nodes.backend.controller.get_user_input",
        lambda *args, **kwargs: pytest.fail("Unexpected folder prompt."),
    )
    ct.set("name", "first")
    ct.ensure_ready()
    default_root = ct.bids_root / "derivatives" / "mne-nodes"
    assert ct.deriv_root == default_root
    assert ct.deriv_root.is_dir()
    assert ct.plot_root is None
    with pytest.raises(RuntimeError, match="Optional plot"):
        ct.ensure_plot_root()
    with pytest.raises(RuntimeError, match="Optional plot"):
        _ = ct.plot_path

    ct.flush()
    reloaded = Controller(config_path=ct.config_path, settings=ct.settings)
    assert reloaded.deriv_root == default_root
    assert reloaded.plot_root is None

    new_config = tmp_path / "second_pipeline.json"
    new_config.write_text(json.dumps({"name": "second"}), encoding="utf-8")
    ct.load_config(new_config)
    ct.ensure_ready()
    assert ct.deriv_root == default_root
    assert ct.plot_root is None

    # Explicit roots keep the legacy layout
    derivative = default_root / "custom"
    derivative.mkdir()
    ct.deriv_root = derivative
    ct.plot_root = tmp_path
    assert ct.ensure_deriv_root(interactive=False) == derivative
    assert ct.ensure_plot_root(interactive=False) == tmp_path
    assert ct.plot_path == tmp_path / ct.name
    ct.plot_root = None
    assert ct.plot_root is None


@pytest.mark.parametrize("action", ["accept", "reject", "unchanged"])
@pytest.mark.parametrize("prompt_for_path", [False, True])
def test_input_directory_change(ct, tmp_path, monkeypatch, action, prompt_for_path):
    old_subjects_dir = ct.ensure_subjects_dir()
    old_bids_root = ct.bids_root
    old_directory = ct.bids_root
    new_directory = tmp_path / "new_input"
    new_directory.mkdir()
    if action == "unchanged":
        new_directory = old_directory
    old_derivatives = ct.ensure_deriv_root()
    ct.plot_root = tmp_path
    selections = {
        "subject": ["old-subject"],
        "eeg": ["old_file.vhdr"],
        "session": ["01"],
    }
    groups = {"old-group": ["old_file.vhdr"]}
    ct.set("selected_inputs", selections.copy())
    ct.set("custom_groups", groups.copy())
    ct.set("coreg_subjects", {"old_file.vhdr": "old-subject"})
    confirmations = []
    monkeypatch.setattr(
        "mne_nodes.backend.controller.ask_user",
        lambda message: confirmations.append(message) or action == "accept",
    )
    monkeypatch.setattr(
        "mne_nodes.backend.controller.get_user_input",
        lambda *args, **kwargs: new_directory,
    )

    ct.bids_root = None if prompt_for_path else new_directory

    assert len(confirmations) == (0 if action == "unchanged" else 1)
    expected_subjects_dir = (
        new_directory / "derivatives" / "freesurfer"
        if action == "accept"
        else old_subjects_dir
    )
    assert os.environ["SUBJECTS_DIR"] == str(expected_subjects_dir)
    if action == "accept":
        expected_selections = {}
        assert ct.bids_root == new_directory
        assert ct.get("selected_inputs") == expected_selections
        assert ct.get("custom_groups") == {}
        assert ct.get("coreg_subjects") == {}
        assert ct.deriv_root is None
        assert ct.plot_root is None
        assert "subject" in confirmations[0]
        ct.flush()
        ct.load()
        assert ct.get("selected_inputs") == expected_selections
    else:
        assert ct.bids_root == old_directory
        assert ct.get("selected_inputs") == selections
        assert ct.get("custom_groups") == groups
        assert ct.get("coreg_subjects") == {"old_file.vhdr": "old-subject"}
        assert ct.deriv_root == old_derivatives
        assert ct.plot_root == tmp_path
    if action == "accept":
        assert ct.subjects_dir is None
        assert ct.ensure_subjects_dir(False) == (
            new_directory / "derivatives" / "freesurfer"
        )
    else:
        assert ct.bids_root == old_bids_root
        assert ct.subjects_dir == old_subjects_dir


def test_explicit_derivatives_root_protects_outputs(ct, tmp_path, monkeypatch):
    """Explicit roots are used directly; failures never redirect or move outputs."""
    external = tmp_path / "old-derivatives"
    external.mkdir()
    marker = external / "existing.txt"
    marker.write_text("unchanged", encoding="utf-8")
    ct.deriv_root = external
    assert ct.deriv_root == external
    assert ct.ensure_deriv_root(False) == external
    assert ct.settings.get("deriv_root") == ct.deriv_root
    ct.flush()
    reloaded = Controller(config_path=ct.config_path, settings=ct.settings)
    assert reloaded.ensure_deriv_root(False) == external
    assert marker.read_text(encoding="utf-8") == "unchanged"
    ct.deriv_root = None
    assert ct.deriv_root == ct.bids_root / "derivatives" / "mne-nodes"
    assert not (ct.deriv_root / marker.name).exists()
    assert marker.read_text(encoding="utf-8") == "unchanged"

    missing = tmp_path / "missing-derivatives"
    with pytest.raises(ValueError, match="deriv_root"):
        ct.deriv_root = missing
    ct.ensure_deriv_root(False)
    ct.settings.set("deriv_root", missing)
    assert ct.deriv_root is None
    with pytest.raises(ValueError, match="deriv_root"):
        ct.ensure_deriv_root(False)
    assert ct.settings.get("deriv_root") == missing
    assert not missing.exists()

    ct.deriv_root = external

    def fail(*args, **kwargs):
        raise OSError("Read-only dataset")

    monkeypatch.setattr(ct, "ensure_deriv_root", fail)
    with pytest.raises(OSError, match="Read-only"):
        ct.deriv_root = None
    assert ct.deriv_root == external


@pytest.mark.parametrize("nested", [False, True])
def test_freesurfer_directory_is_dataset_local(ct, tmp_path, monkeypatch, nested):
    """Ignore device/global subjects settings and derive the folder from the dataset."""
    external = tmp_path / "global-subjects"
    external.mkdir()
    ct.settings.set("subjects_dir", external)
    mne.set_config("SUBJECTS_DIR", str(external), home_dir=tmp_path, set_env=False)
    mne_config = Path(mne.get_config_path(home_dir=tmp_path))
    original_config = mne_config.read_bytes()
    monkeypatch.setenv("SUBJECTS_DIR", str(external))
    monkeypatch.setattr(
        "mne_nodes.backend.controller.mne.set_config",
        lambda *args, **kwargs: pytest.fail("Do not modify global MNE settings."),
    )
    assert ct.subjects_dir is None
    assert ct.get_datatype_items("subject") == []
    expected = ct.bids_root / "derivatives" / "freesurfer"
    if nested:
        expected /= "subjects"
        expected.mkdir(parents=True)
    reloaded = Controller(config_path=ct.config_path, settings=ct.settings)
    assert os.environ["SUBJECTS_DIR"] == str(expected)
    assert reloaded.bids_root == ct.bids_root
    assert ct.ensure_subjects_dir(False) == expected
    assert ct.subjects_dir == expected
    assert os.environ["SUBJECTS_DIR"] == str(expected)
    assert mne.get_config("SUBJECTS_DIR", home_dir=tmp_path) == str(expected)
    assert mne.utils.get_subjects_dir() == expected
    assert mne.utils.get_subjects_dir(external) == external
    assert mne_config.read_bytes() == original_config
    assert mne.get_config("SUBJECTS_DIR", home_dir=tmp_path, use_env=False) == str(
        external
    )
    assert ct.settings.get("subjects_dir") == external
    custom = ct.deriv_root / "custom"
    custom.mkdir()
    ct.deriv_root = custom
    assert ct.subjects_dir == expected
    ct.deriv_root = external
    assert ct.ensure_subjects_dir(False) == expected
    assert not (external / "freesurfer").exists()
    for folder in ("mri", "surf", "label"):
        (expected / "sub-01" / folder).mkdir(parents=True)
    assert ct.get_datatype_items("subject") == ["sub-01"]
    ct.subjects_dir = expected
    ct.subjects_dir = external
    assert ct.ensure_subjects_dir(False) == external
    assert os.environ["SUBJECTS_DIR"] == str(external)
    assert ct.parameter("subjects_dir", "unused") == external
    assert ct.get_datatype_items("subject") == []
    reloaded = Controller(config_path=ct.config_path, settings=ct.settings)
    assert reloaded.subjects_dir == external
    missing = tmp_path / "missing-subjects"
    with pytest.raises(ValueError, match="subjects_dir"):
        ct.subjects_dir = missing
    assert ct.subjects_dir == external
    assert os.environ["SUBJECTS_DIR"] == str(external)
    assert not missing.exists()

    original_root = ct.bids_root
    other_dataset = tmp_path / "other-dataset"
    other_dataset.mkdir()
    ct.bids_root = other_dataset
    assert ct.subjects_dir is None
    assert os.environ["SUBJECTS_DIR"] == str(
        other_dataset / "derivatives" / "freesurfer"
    )
    ct.subjects_dir = expected
    ct.bids_root = original_root
    assert ct.subjects_dir == external
    assert os.environ["SUBJECTS_DIR"] == str(external)
    external.rmdir()
    with pytest.raises(ValueError, match="subjects_dir"):
        ct.ensure_subjects_dir(False)
    assert not external.exists()
    assert os.environ["SUBJECTS_DIR"] == str(external)
    ct.subjects_dir = None
    assert ct.ensure_subjects_dir(False) == expected
    assert os.environ["SUBJECTS_DIR"] == str(expected)
    assert ct.get_datatype_items("subject") == ["sub-01"]
    assert mne_config.read_bytes() == original_config


def test_load_missing_plugin_metadata(ct, tmp_path, monkeypatch):
    class DummyViewer:
        def load_nodes(self, *_args, **_kwargs):
            return None

    imported_nodes = {"nodes": {"input": {"name": "Input-0"}}, "connections": {}}
    import_payload = {
        "node_config": imported_nodes,
        "plugin_meta": {
            "test_module": {
                "plugin_github": "https://github.com/org/test_module",
                "plugin_type": "github",
            }
        },
        "parameters": {"test_func1": {"a": 12}},
    }
    import_path = tmp_path / "pipeline_import_missing_module.json"
    with open(import_path, "w") as file:
        json.dump(import_payload, file, indent=4, cls=TypedJSONEncoder)

    loaded_plugins = []
    monkeypatch.setattr(
        ct, "load_plugin_github", lambda plugin_url: loaded_plugins.append(plugin_url)
    )
    viewer = DummyViewer()
    monkeypatch.setattr(type(ct), "viewer", property(lambda self: viewer))

    ct.config_path = import_path

    assert loaded_plugins == ["https://github.com/org/test_module"]
    assert ct.get("node_config") == imported_nodes


@pytest.mark.parametrize("with_script", [False, True])
def test_expose_plugin_functions(tmp_path, monkeypatch, with_script):
    """Metadata exposes submodule functions; plugin/script overrides take precedence."""
    from types import ModuleType

    import mne

    plugin = ModuleType("submodule_plugin")
    script_path = None
    if with_script:
        script_path = tmp_path / "submodule_plugin.py"
        script_path.write_text("from mne import *\n", encoding="utf-8")
        plugin.__file__ = str(script_path)
        exec(  # noqa: S102
            compile(script_path.read_text(), str(script_path), "exec"), plugin.__dict__
        )
    assert not hasattr(plugin, "make_watershed_bem")
    functions = {
        "make_watershed_bem": {"module_name": "mne.bem", "class_name": None},
        "read_bem_surfaces": {"module_name": "mne", "class_name": None},
        "Raw.filter": {"module_name": "mne.io", "class_name": "Raw"},
    }

    Controller._expose_plugin_functions(plugin, functions, script_path)

    assert plugin.make_watershed_bem is mne.bem.make_watershed_bem
    assert plugin.read_bem_surfaces is mne.read_bem_surfaces
    assert not hasattr(plugin, "Raw.filter")

    def wrapper():
        return "plugin override"

    override = ModuleType("override_plugin")
    override_script = tmp_path / "override_plugin.py"
    override_script.write_text("", encoding="utf-8")
    override.__file__ = str(override_script)
    if with_script:
        override.__path__ = [str(tmp_path)]
        script_module = ModuleType("override_plugin.override_plugin")
        script_module.make_watershed_bem = wrapper
        monkeypatch.setitem(sys.modules, script_module.__name__, script_module)
    else:
        override.make_watershed_bem = wrapper
    Controller._expose_plugin_functions(
        override,
        {"make_watershed_bem": functions["make_watershed_bem"]},
        override_script,
    )
    assert override.make_watershed_bem is wrapper


def test_codegen_submodule_function_executes(ct, monkeypatch):
    """Generated plugin calls resolve to the configured submodule function."""
    from types import ModuleType
    from unittest.mock import Mock

    from mne.bem import make_watershed_bem

    import mne_nodes
    from mne_nodes.backend.code_generation import CodeGenerator

    plugin = ModuleType("bem_plugin")
    func_meta = {
        "inputs": {"subject": {"accepted_ports": ["subject"], "optional": False}},
        "outputs": {},
        "parameters": {},
        "target": "file",
        "module_name": "mne.bem",
        "class_name": None,
    }
    ct.load_plugin(
        plugin, "bem_plugin", {"config_path": {"make_watershed_bem": func_meta}}
    )
    assert plugin.make_watershed_bem is make_watershed_bem
    ct.set("selected_inputs", {"eeg": [ct.get_datatype_items("eeg")[0]]})
    node_sequence = {
        "file": [
            {
                "name": "make_watershed_bem",
                "class": "FunctionNode",
                "inputs": {"subject": ["Input-0"]},
                "outputs": {},
                "checked": False,
                "function_meta": ct.get_function_meta("make_watershed_bem"),
            }
        ],
        "group": [],
    }
    code = CodeGenerator(ct, node_sequence).code
    watershed = Mock()
    monkeypatch.setattr(plugin, "make_watershed_bem", watershed)
    monkeypatch.setattr(ct, "load_recording_subject", lambda bp: "fsaverage")
    monkeypatch.setattr("mne_nodes.backend.controller.Controller", lambda **kwargs: ct)
    monkeypatch.setattr(mne_nodes, "gui_mode", False)

    exec(compile(code, "<generated-pipeline>", "exec"), {})  # noqa: S102

    watershed.assert_called_once_with(subject="fsaverage")


@pytest.mark.parametrize("save_as_method", ["save_config_as", "export_pipeline"])
def test_config_file_actions_roundtrip(ct, tmp_path, save_as_method):
    """New, save, save-as/export and load preserve the complete pipeline state."""
    new_config_path = tmp_path / "new_config.json"
    export_path = tmp_path / "pipeline_roundtrip.json"
    ct.new_config(new_config_path)
    ct.set("name", "draft")
    roundtrip_nodes = {
        "nodes": {"input": {"name": "Input-0"}, "filter": {"name": "test_filter"}},
        "connections": {"conn_0": {"source": "Input-0", "target": "filter"}},
    }
    roundtrip_parameters = {
        "test_filter": {"l_freq": 1.0, "h_freq": 40.0},
        "test_epochs": {"tmin": -0.2, "tmax": 0.5},
    }
    ct.set("parameters", roundtrip_parameters)
    ct.set("node_config", roundtrip_nodes)

    ct.save_config()
    assert json.loads(new_config_path.read_text(encoding="utf-8"))["name"] == "draft"
    getattr(ct, save_as_method)(export_path)
    assert ct.config_path == export_path
    assert json.loads(export_path.read_text(encoding="utf-8"))["name"] == "draft"

    ct.set("parameters", {})
    ct.set("node_config", {})
    ct.load_config(export_path)

    assert ct.get("name") == "draft"
    assert ct.get("parameters") == roundtrip_parameters
    assert ct.get("node_config") == roundtrip_nodes


@pytest.mark.timeout(180)
@pytest.mark.parametrize("storage", ["memory", "local", "external"])
def test_codegen_pipeline(qtbot, tmp_path, monkeypatch, settings, storage):
    from mne_nodes.backend.code_generation import CodeGenerator
    from mne_nodes.gui.node.node_viewer import NodeViewer
    from tests.conftest import _add_complex_nodes, create_test_controller

    monkeypatch.setattr(Controller, "load_recent_plugins", lambda self: self.plugins)
    ct = create_test_controller(
        settings=settings, tmp_path=tmp_path, monkeypatch=monkeypatch
    )
    default_plugin = next(iter(ct.plugins))
    for function_meta in ct.function_meta.values():
        function_meta.setdefault("class_name", None)
        function_meta.setdefault("plugin_name", default_plugin)

    viewer = NodeViewer(ct)
    qtbot.addWidget(viewer)
    _add_complex_nodes(viewer)

    eeg_files = []
    for extension in (".vhdr", ".edf", ".bdf", ".set"):
        eeg_files = sorted(ct.bids_root.rglob(f"*_eeg{extension}"))
        if len(eeg_files) > 0:
            break
    assert len(eeg_files) > 0, "tiny_bids fixture should provide at least one EEG file"

    if storage == "external":
        external = tmp_path / "separate-derivatives"
        external.mkdir()
        ct.deriv_root = external
    derivative_root = ct.ensure_deriv_root()
    ct.set("selected_inputs", {"eeg": [eeg_files[0].name]})
    ct.flush()

    node_sequence = viewer.get_node_sequence(viewer.input_node)
    for sequence in node_sequence.values():
        for node in sequence:
            node["checked"] = storage != "memory"

    generated_code = CodeGenerator(ct, node_sequence).code
    validation_config_path = Path(__file__).parent / "validation_functions_config.json"
    generated_code = generated_code.replace(
        "# Load controller\n",
        "# Load controller\nController.load_recent_plugins = lambda self: self.plugins\n",
        1,
    )
    generated_code = generated_code.replace(
        "\n\n# Inject plugins into global namespace\n",
        (
            f"\nct.load_plugin_path('{validation_config_path.as_posix()}')\n\n"
            "# Inject plugins into global namespace\n"
        ),
        1,
    )
    script_path = tmp_path / "generated_pipeline.py"
    script_path.write_text(generated_code, encoding="utf-8")

    env = os.environ.copy()
    env["MPLBACKEND"] = "Agg"
    completed = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True,
        text=True,
        env=env,
        timeout=180,
        check=False,
    )
    assert completed.returncode == 0, (
        "Generated script failed.\n"
        f"STDOUT:\n{completed.stdout}\n"
        f"STDERR:\n{completed.stderr}"
    )
    if storage != "memory":
        import mne
        from mne_bids import get_bids_path_from_fname

        source = get_bids_path_from_fname(eeg_files[0])
        epochs_path = (
            source.copy().update(root=derivative_root, suffix="epo", check=False).fpath
        )
        evoked_path = (
            source.copy().update(root=derivative_root, suffix="ave", check=False).fpath
        )
        assert epochs_path.is_file()
        assert evoked_path.is_file()
        assert len(mne.read_epochs(epochs_path)) > 0
        assert len(mne.read_evokeds(evoked_path)) > 0


# ToDo: add a test about accessing config-variables with .get from Base-Widgets with permanent reference

# ToDo: add a test about accessing and modifying config from multiple processes without data loss or race conditions


def test_plugin_relocation_uses_device_settings(ct, tmp_path, make_plugin, monkeypatch):
    """Re-selected plugin paths are stored per device and override stale configs."""
    plugin_name = "relocate_plugin"
    new_plugin_dir = tmp_path / "new_location"
    new_config_path, new_script_path = make_plugin(new_plugin_dir, plugin_name)
    missing_path = tmp_path / "old_location" / f"{plugin_name}_config.json"

    monkeypatch.setattr(
        "mne_nodes.backend.controller.raise_user_attention", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "mne_nodes.backend.controller.get_user_input", lambda *a, **k: new_config_path
    )

    ct.load_plugin_path(missing_path)

    assert plugin_name in ct.plugins
    plugin_config = ct.settings.get("plugin_config") or {}
    assert plugin_name in plugin_config
    assert Path(plugin_config[plugin_name]["config_path"]) == new_config_path
    assert Path(plugin_config[plugin_name]["script_path"]) == new_script_path

    # A stale path in the pipeline config must not override the device path
    ct.set_dict_value(
        "plugin_meta",
        plugin_name,
        {
            "config_path": missing_path,
            "script_path": missing_path.parent / f"{plugin_name}.py",
            "plugin_type": "path",
        },
    )
    loaded_paths = []
    original = ct.load_plugin_path

    def capture_load(config_path, **kwargs):
        loaded_paths.append(Path(config_path))
        return original(config_path, **kwargs)

    monkeypatch.setattr(ct, "load_plugin_path", capture_load)
    ct.load_recent_plugins()
    assert new_config_path in loaded_paths
    assert missing_path not in loaded_paths


@pytest.mark.parametrize("already_relocated", [False, True])
def test_relocated_plugin_identity_survives_restart(
    ct, tmp_path, make_plugin, monkeypatch, already_relocated
):
    """A declared display name replaces its legacy path registration only once."""
    config_path, script_path = make_plugin(tmp_path / "relocated", "legacy_plugin")
    (config_path.parent / "__init__.py").write_text(
        f'PLUGIN_NAME = "display-plugin"\nCONFIG_PATH = {str(config_path)!r}\n',
        encoding="utf-8",
    )
    stale = tmp_path / "missing" / config_path.name
    meta = {
        "plugin_type": "path",
        "config_path": stale,
        "script_path": stale.with_name(script_path.name),
    }
    ct.set("plugin_meta", {"legacy_plugin": meta})
    if already_relocated:
        ct.set_dict_value(
            "plugin_meta", "display-plugin", {**meta, "config_path": config_path}
        )
        ct.settings.set(
            "plugin_config",
            {
                "display-plugin": {
                    "config_path": config_path,
                    "script_path": script_path,
                }
            },
        )
    prompts = []

    def relocate(*args, **kwargs):
        prompts.append(True)
        return config_path

    monkeypatch.setattr("mne_nodes.backend.controller.get_user_input", relocate)
    ct.load_recent_plugins()
    assert prompts == ([] if already_relocated else [True])
    assert set(ct.get("plugin_meta")) == {"display-plugin"}
    assert set(ct.plugins) >= {"display-plugin"}
    assert "legacy_plugin" not in ct.plugins

    from mne_nodes.backend.controller import Controller
    from mne_nodes.backend.settings import Settings

    ct.flush()  # MainWindow flushes the project when closing.
    restarted = Controller(config_path=ct.config_path, settings=Settings())
    assert set(restarted.get("plugin_meta")) == {"display-plugin"}
    assert set(restarted.plugins) == {"display-plugin"}
    assert prompts == ([] if already_relocated else [True])


def test_codegen_multi_type_read_write(ct, caplog):
    import logging

    from mne_nodes.backend.code_generation import CodeGenerator

    plugin_name = next(iter(ct.plugins), "mne_functions")

    # Register metadata for grand_average with dict-based read and write
    ct.function_meta["grand_average"] = {
        "inputs": {
            "all_inst": {
                "accepted_ports": ["all_inst", "evoked", "evokeds", "tfr"],
                "optional": False,
                "read": {
                    "evoked": "read_evokeds",
                    "evokeds": "read_evokeds",
                    "tfr": "read_tfrs",
                },
                "suffix": {"evoked": "ave", "evokeds": "ave", "tfr": "tfr"},
            }
        },
        "parameters": {},
        "outputs": {
            "grand_average": {
                "accepted_ports": ["grand_average", "evoked", "evokeds", "tfr"],
                "write": {
                    "evoked": "write_evokeds",
                    "evokeds": "write_evokeds",
                    "tfr": "write_tfrs",
                },
                "suffix": {"evoked": "ave", "evokeds": "ave", "tfr": "tfr"},
            }
        },
        "target": "group",
        "category": "sensor_space",
        "sub_category": None,
        "class_name": None,
        "module_name": "mne",
        "plugin": plugin_name,
    }
    ct.function_meta["read_evokeds"] = {
        "parameters": {"fname": None},
        "class_name": None,
        "module_name": "mne",
        "plugin": plugin_name,
    }
    ct.function_meta["write_evokeds"] = {
        "parameters": {"fname": None},
        "class_name": None,
        "module_name": "mne",
        "plugin": plugin_name,
    }

    ct.set("selected_inputs", {"subject": ["sub-01", "sub-02"]})

    node_sequence = {
        "file": [],
        "group": [
            {
                "name": "grand_average",
                "class": "FunctionNode",
                "inputs": {"all_inst": ["test_evokeds"]},
                "input_ports": {"all_inst": ["evoked"]},
                "outputs": {"grand_average": ["evoked"]},
                "output_ports": {"grand_average": ["evoked"]},
                "checked": True,
                "function_meta": ct.function_meta["grand_average"],
            }
        ],
    }

    gen = CodeGenerator(ct, node_sequence)
    code = gen.code
    assert "read_evokeds" in code
    assert "suffix='ave'" in code
    assert "write_evokeds" in code
    assert "grand_average(" in code

    node = node_sequence["group"][0]
    node["inputs"] = {"all_inst": ["unknown_node"]}
    node["input_ports"] = {"all_inst": ["unknown_port"]}
    with caplog.at_level(logging.WARNING, logger="mne_nodes"):
        CodeGenerator(ct, node_sequence)
    assert any("not valid" in record.message for record in caplog.records)
