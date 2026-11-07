"""Coregistration discovery, fitting, saving and Qt integration tests."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import mne
import numpy as np
import pytest
import pyvista
from mne_bids import BIDSPath, write_raw_bids
from qtpy.QtCore import QObject, Signal
from qtpy.QtWidgets import QPushButton

from mne_nodes.backend import coregistration as backend
from mne_nodes.backend.controller import Controller
from mne_nodes.backend.execution import WorkerSignals
from mne_nodes.gui.dialogs import coreg_dialog


def make_info(offset=0.0):
    """Make real MNE digitization without requiring a dataset download."""
    info = mne.create_info(["EEG001"], 100, "eeg")
    montage = mne.channels.make_dig_montage(
        ch_pos={"EEG001": [0.0, 0.0, 0.09 + offset]},
        nasion=[0.0, 0.1, 0.0],
        lpa=[-0.08, 0.0, 0.0],
        rpa=[0.08, 0.0, 0.0],
        hsp=[[0.01, 0.02, 0.09]],
        coord_frame="head",
    )
    info.set_montage(montage)
    return info


def make_path(root, run="01", session="01", subject="01", datatype="eeg"):
    """Make a raw BIDS path with a recording-specific run."""
    return BIDSPath(
        root=root,
        subject=subject,
        session=session,
        task="test",
        run=run,
        datatype=datatype,
        suffix=datatype,
        extension=".fif",
        check=False,
    )


def make_group(root, count=2):
    """Make one group of verified matching recordings."""
    return backend.CoregGroup(
        [
            backend.CoregRecording(make_path(root, str(n + 1).zfill(2)), make_info())
            for n in range(count)
        ]
    )


def make_controller(tmp_path):
    """Create an in-memory controller exposing the dialog's public dependencies."""
    subjects_dir = tmp_path / "subjects"
    subjects_dir.mkdir(exist_ok=True)
    values = {}
    controller = Mock(spec=Controller)
    controller.configure_mock(
        raw_types=["eeg", "meg", "ieeg"],
        ensure_bids_root=Mock(return_value=tmp_path / "bids"),
        ensure_deriv_root=Mock(return_value=tmp_path / "derivatives"),
        other_derivative_roots=Mock(return_value=[]),
        ensure_subjects_dir=Mock(return_value=subjects_dir),
        get_datatype_items=Mock(
            side_effect=lambda dt: ["sub-01"] if dt == "subject" else []
        ),
        get=lambda key, default=None: values.get(key, default),
        set=lambda key, value: values.__setitem__(key, value),
    )
    return controller


def write_trans_file(path: Path) -> Path:
    """Write an identity head-to-MRI transformation to ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    mne.write_trans(path, mne.transforms.Transform("head", "mri"), overwrite=True)
    return path


def test_digitization_exact_comparison():
    """Missing, moved, reordered or differently identified points never match."""
    info = make_info()
    assert backend.identical_digitization(info, info.copy())
    assert not backend.identical_digitization(info, make_info(0.001))
    assert not backend.identical_digitization(info, mne.create_info(["x"], 100, "eeg"))
    changed = info.copy()
    changed["dig"][0]["ident"] += 1
    assert not backend.identical_digitization(info, changed)
    changed = info.copy()
    changed["dig"].reverse()
    assert not backend.identical_digitization(info, changed)


def test_discover_groups(tmp_path, monkeypatch):
    """Group only identical points within a subject/session, across raw types."""
    ct = make_controller(tmp_path)
    paths = [
        make_path(tmp_path, "01"),
        make_path(tmp_path, "02"),
        make_path(tmp_path, "03"),
        make_path(tmp_path, "01", session="02"),
        make_path(tmp_path, "01", subject="02"),
        make_path(tmp_path, "04"),
        make_path(tmp_path, "05"),
        make_path(tmp_path, "06"),
        make_path(tmp_path, "01", datatype="meg"),
    ]
    infos = {p.fpath.name: make_info() for p in paths}
    infos[paths[2].fpath.name] = make_info(0.001)
    infos[paths[5].fpath.name] = mne.create_info(["x"], 100, "eeg")
    infos[paths[6].fpath.name] = mne.create_info(["x"], 100, "eeg")
    ct.get_datatype_items.side_effect = lambda dt: [
        p.basename for p in paths if p.datatype == dt
    ]

    def read_info(fname):
        fname = Path(fname)
        if fname.name == paths[7].fpath.name:
            raise OSError("Cannot read recording")
        return infos[fname.name]

    monkeypatch.setattr(backend.mne.io, "read_info", read_info)
    signals = WorkerSignals()
    progress = Mock()
    signals.pgbar_n.connect(progress)
    groups = backend.discover_coreg_groups(ct, signals)
    assert [len(g.recordings) for g in groups] == [3, 1, 1, 1, 1, 1, 1]
    assert len([g for g in groups if g.recordings[0].error]) == 3
    assert progress.call_args.args == (len(paths),)

    # Failed transformation lookups are warnings, not digitization errors.
    monkeypatch.setattr(
        backend, "find_trans", Mock(side_effect=ValueError("ambiguous candidates"))
    )
    recording = backend.discover_coreg_groups(ct, WorkerSignals())[0].recordings[0]
    assert recording.error is None
    assert recording.warning == "Transformation lookup failed: ambiguous candidates"

    signals = WorkerSignals()
    signals.was_canceled = True
    assert backend.discover_coreg_groups(ct, signals) == []


def test_discover_real_bids_headers(tmp_path):
    """Read actual FIF BIDS headers through the public MNE-BIDS reader."""
    ct = make_controller(tmp_path)
    info = make_info()
    raw = mne.io.RawArray(np.zeros((1, 100)), info)
    raw.add_channels(
        [mne.io.RawArray(np.zeros((1, 100)), mne.create_info(["MEG001"], 100, "mag"))]
    )
    raw.drop_channels(["EEG001"])
    path = make_path(ct.ensure_bids_root(), datatype="meg")
    written = write_raw_bids(
        raw, path, allow_preload=True, format="FIF", overwrite=True
    )
    ct.get_datatype_items.side_effect = lambda dt: (
        [written.basename] if dt == "meg" else []
    )
    groups = backend.discover_coreg_groups(ct, WorkerSignals())
    assert len(groups) == 1
    recording = groups[0].recordings[0]
    assert recording.error is None
    assert recording.info is not None
    assert recording.info["dig"]
    assert recording.bids_path.fpath == written.fpath


def test_trans_paths_and_lookup(tmp_path):
    """Keep BIDS entities, find session files and never pick ambiguous ones."""
    path = make_path(tmp_path)
    root = tmp_path / "derivatives"
    canonical = backend.trans_path(path, root)
    assert canonical == (
        root / "sub-01" / "ses-01" / "eeg" / "sub-01_ses-01_task-test_run-01_trans.fif"
    )
    split = path.copy().update(split="01")
    assert backend.trans_path(split, root) == canonical
    assert backend.find_trans(path, root) is None
    session_path = write_trans_file(
        path.copy()
        .update(
            root=root,
            task=None,
            run=None,
            suffix="trans",
            extension=".fif",
            check=False,
        )
        .fpath
    )
    assert backend.find_trans(path, root) == session_path
    write_trans_file(
        path.copy().update(root=root, run=None, suffix="trans", check=False).fpath
    )
    with pytest.raises(ValueError, match="Ambiguous"):
        backend.find_trans(path, root)
    write_trans_file(canonical)
    assert backend.find_trans(path, root) == canonical
    assert backend.find_trans(make_path(tmp_path, session="02"), root) is None


def test_find_trans_in_other_derivative_pipelines(ct, tmp_path):
    """Find legacy transformations from preceding software in other folders."""
    derivatives = ct.bids_root / "derivatives"
    for name in ("freesurfer", "mne-pipeline-hd", "mne-bids-pipeline"):
        (derivatives / name).mkdir(parents=True, exist_ok=True)
    roots = ct.other_derivative_roots()
    assert derivatives / "mne-pipeline-hd" in roots
    assert derivatives / "mne-bids-pipeline" in roots
    assert ct.ensure_deriv_root(False) not in roots
    assert derivatives / "freesurfer" not in roots

    path = make_path(tmp_path, run="1", datatype="meg")
    own = tmp_path / "derivatives" / "mne-nodes"
    legacy_root = tmp_path / "derivatives" / "mne-pipeline-hd"
    session = legacy_root / "sub-01" / "ses-01"
    legacy = write_trans_file(session / "sub-01_ses-01_task-test_run-01-trans.fif")
    write_trans_file(session / "sub-01_ses-01_task-other_run-01-trans.fif")
    write_trans_file(session / "eeg" / "sub-01_ses-01_trans.fif")
    assert backend.find_trans(path, None, [legacy_root]) == legacy
    assert backend.find_trans(path, own, [legacy_root]) == legacy
    other_root = tmp_path / "derivatives" / "other-software"
    write_trans_file(other_root / "sub-01" / "ses-01" / "sub-01_ses-01_trans.fif")
    with pytest.raises(ValueError, match="Ambiguous"):
        backend.find_trans(path, own, [legacy_root, other_root])
    preferred = write_trans_file(backend.trans_path(path, own))
    assert backend.find_trans(path, own, [legacy_root, other_root]) == preferred


def test_save_group_and_overwrite_guard(tmp_path):
    """Persist a real transform per recording and preflight replacement."""
    group = make_group(tmp_path)
    trans = mne.transforms.Transform("head", "mri")
    root = tmp_path / "derivatives"
    with pytest.raises(ValueError, match="head-to-MRI"):
        backend.save_group_trans(group, mne.transforms.Transform("meg", "mri"), root)
    paths = backend.save_group_trans(group, trans, root)
    assert len(paths) == 2
    for recording, path in zip(group.recordings, paths):
        assert recording.existing_trans == path
        loaded = mne.read_trans(path)
        assert isinstance(loaded, mne.transforms.Transform)
        np.testing.assert_array_equal(loaded["trans"], trans["trans"])
    with pytest.raises(FileExistsError):
        backend.save_group_trans(group, trans, root)
    backend.save_group_trans(group, trans, root, overwrite=True)
    group.recordings[1].info = make_info(0.001)
    with pytest.raises(ValueError, match="different digitizations"):
        backend.save_group_trans(group, trans, root, overwrite=True)
    assert not list((tmp_path / "other").glob("**/*"))


@pytest.mark.parametrize("outcome", ["success", "cancel", "failure"])
def test_automatic_recipe(tmp_path, monkeypatch, outcome):
    """Verify tutorial stages and that cancellation/failure save nothing."""
    group = make_group(tmp_path)
    signals = WorkerSignals()
    coreg = Mock()
    coreg.trans = mne.transforms.Transform("head", "mri")
    coreg.compute_dig_mri_distances.return_value = np.array([0.001, 0.002, 0.003])
    factory = Mock(return_value=coreg)
    monkeypatch.setattr(mne.coreg, "Coregistration", factory)
    signals.was_canceled = outcome == "cancel"
    if outcome == "failure":
        coreg.fit_icp.side_effect = RuntimeError("fit failed")
        with pytest.raises(RuntimeError, match="fit failed"):
            backend.automatic_coregistration(
                group, "sub-01", tmp_path, tmp_path / "derivatives", signals
            )
        assert not (tmp_path / "derivatives").exists()
        return
    result = backend.automatic_coregistration(
        group, "sub-01", tmp_path, tmp_path / "derivatives", signals
    )
    if outcome == "cancel":
        assert "canceled" in result
        coreg.fit_fiducials.assert_not_called()
        assert not (tmp_path / "derivatives").exists()
    else:
        assert factory.call_args.kwargs["fiducials"] == "estimated"
        coreg.fit_fiducials.assert_called_once_with(verbose=True)
        assert [c.kwargs for c in coreg.fit_icp.call_args_list] == [
            {"n_iterations": 6, "nasion_weight": 2.0, "verbose": True},
            {"n_iterations": 20, "nasion_weight": 10.0, "verbose": True},
        ]
        coreg.omit_head_shape_points.assert_called_once_with(distance=0.005)
        assert "2.00 / 1.00 / 3.00 mm" in result
        assert all(
            r.existing_trans is not None and r.existing_trans.is_file()
            for r in group.recordings
        )


class CloseSignals(QObject):
    """Qt close signal used by the manual-GUI test double."""

    signal_close = Signal()


def make_manual_ui():
    """Emulate the observed MNE Qt button and widget wrapper contract."""
    button = QPushButton("Save...")
    button.clicked.connect(Mock())  # MNE's original file picker.
    ui = SimpleNamespace(
        coreg=SimpleNamespace(trans=mne.transforms.Transform("head", "mri")),
        _widgets={"save_trans": SimpleNamespace(_widget=button)},
        _trans_modified=True,
        _display_message=Mock(),
        observe=Mock(),
        _renderer=SimpleNamespace(_window=CloseSignals(), show=Mock()),
        close=Mock(),
    )
    for name in (
        "subjects_dir",
        "subjects_dir_field",
        "subject",
        "info_file",
        "info_file_field",
        "scaling_mode",
    ):
        ui._widgets[name] = Mock()
    return ui, button


def test_manual_open_uses_bids_info_and_cleans_up(qtbot, tmp_path, monkeypatch):
    """Non-FIF BIDS digitization survives export; resources live until actual close."""
    ct = make_controller(tmp_path)
    dialog = coreg_dialog.CoregDialog(ct)
    qtbot.addWidget(dialog)
    dialog.mri_subject.addItems(["", "sub-01"])
    group = make_group(tmp_path)
    dialog._discovered([group])
    ui, button = make_manual_ui()
    qtbot.addWidget(button)
    factory = Mock(return_value=ui)
    monkeypatch.setattr(mne.gui, "coregistration", factory)
    monkeypatch.setattr(mne.viz, "set_3d_backend", Mock())
    dialog._open_manual()
    info_path = Path(factory.call_args.kwargs["inst"])
    exported = mne.io.read_info(info_path)["dig"]
    original = group.info["dig"]
    assert len(exported) == len(original)
    for actual, expected in zip(exported, original):
        for key in ("kind", "ident", "coord_frame"):
            assert actual[key] == expected[key]
        np.testing.assert_allclose(actual["r"], expected["r"], atol=1e-8, rtol=0)
    ui._renderer._window.signal_close.emit()
    assert not info_path.exists()
    assert dialog._manual is None


def make_mri_surface(subjects_dir):
    """Create a synthetic FreeSurfer head surface and MRI fiducials."""
    from mne.surface import _get_ico_surface

    subject_dir = subjects_dir / "sub-01"
    (subject_dir / "surf").mkdir(parents=True)
    (subject_dir / "bem").mkdir()
    surface = _get_ico_surface(5)
    assert isinstance(surface, dict)
    mne.write_surface(
        subject_dir / "surf" / "lh.seghead", surface["rr"] * 100, surface["tris"]
    )
    fids = [point.copy() for point in make_info()["dig"] if point["kind"] == 1]
    for point in fids:
        point["coord_frame"] = mne.io.constants.FIFF.FIFFV_COORD_MRI
    mne.io.write_fiducials(
        subject_dir / "bem" / "sub-01-fiducials.fif", fids, coord_frame="mri"
    )
    return subject_dir


def test_automatic_real_mne_fit(tmp_path, monkeypatch):
    """Run real fiducial and ICP fits on a synthetic MRI without dataset downloads."""
    ct = make_controller(tmp_path)
    make_mri_surface(ct.ensure_subjects_dir())
    original_factory = mne.coreg.Coregistration

    def create_coreg(info, subject, subjects_dir, fiducials):
        assert fiducials == "estimated"
        return original_factory(
            info, subject, subjects_dir=subjects_dir, fiducials="auto"
        )

    monkeypatch.setattr(mne.coreg, "Coregistration", create_coreg)
    group = make_group(tmp_path)
    result = backend.automatic_coregistration(
        group,
        "sub-01",
        ct.ensure_subjects_dir(),
        ct.ensure_deriv_root(),
        WorkerSignals(),
    )
    assert "Saved 2 transformation(s)" in result
    assert "mm" in result
    for recording in group.recordings:
        assert recording.existing_trans is not None
        trans = mne.read_trans(recording.existing_trans)
        assert isinstance(trans, mne.transforms.Transform)
        assert np.isfinite(trans["trans"]).all()


def test_manual_real_mne_gui(qtbot, tmp_path, monkeypatch):
    """Exercise the installed MNE Qt save and close hooks on a synthetic MRI."""
    ct = make_controller(tmp_path)
    make_mri_surface(ct.ensure_subjects_dir())
    dialog = coreg_dialog.CoregDialog(ct)
    qtbot.addWidget(dialog)
    dialog.mri_subject.addItems(["", "sub-01"])
    group = make_group(tmp_path)
    dialog._discovered([group])
    errors = []

    class CaptureError:
        def __init__(self, error, *args, **kwargs):
            errors.append(str(error))

        def exec(self):
            pass

    monkeypatch.setattr(
        "mne_nodes.backend.exception_handling.ErrorDialog", CaptureError
    )
    monkeypatch.setattr(pyvista, "OFF_SCREEN", False)
    dialog._open_manual()
    assert not errors, errors
    ui = dialog._manual
    assert ui is not None
    try:
        ui._set_lock_fids(False)
        ui._set_lock_fids(True)
        assert not ui._widgets["info_file"].is_enabled()
        assert not ui._widgets["scaling_mode"].is_enabled()
        ui._forward_widget_command("save_trans", "set_value", None)
        assert not errors, errors
        assert not ui._trans_modified
        assert all(
            r.existing_trans is not None and r.existing_trans.is_file()
            for r in group.recordings
        )
        # Declining the overwrite prompt must keep existing files untouched.
        monkeypatch.setattr(coreg_dialog, "ask_user", lambda *args, **kwargs: False)
        ui._trans_modified = True
        ui._forward_widget_command("save_trans", "set_value", None)
        assert ui._trans_modified
        monkeypatch.setattr(coreg_dialog, "ask_user", lambda *args, **kwargs: True)
        ui._trans_modified = True
        ui._close_dialog_callback("Save")
        assert not errors, errors
        assert not ui._trans_modified
        assert ui._accept_close_event
    finally:
        ui._trans_modified = False
        ui._mri_fids_modified = False
        ui.close()
    assert dialog._manual is None
    assert dialog._manual_files is None
