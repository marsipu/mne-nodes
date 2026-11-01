"""Sample BIDS imports expose anatomy, segmentation and head-to-MRI transforms."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import mne
import nibabel as nib
import numpy as np
import pytest
from mne_bids import BIDSPath
from qtpy.QtCore import Qt

from mne_nodes.backend import data_import
from mne_nodes.backend.coregistration import trans_path


@pytest.fixture
def sample_source(tmp_path):
    """Build a tiny sample-shaped MRI/FreeSurfer tree without dataset downloads."""
    root = tmp_path / "MNE-sample-data"
    subject = root / "subjects" / "sample"
    for folder in ("mri", "surf", "label", "bem"):
        (subject / folder).mkdir(parents=True)
        (subject / folder / "contents.txt").write_text(folder, encoding="utf-8")
    (subject / "bem" / "sample-head.fif").write_bytes(b"scalp")
    image = nib.MGHImage(np.zeros((4, 4, 4), dtype=np.float32), np.eye(4))
    nib.save(image, subject / "mri" / "T1.mgz")
    meg = root / "MEG" / "sample"
    meg.mkdir(parents=True)
    mne.write_trans(
        meg / "sample_audvis_raw-trans.fif", mne.transforms.Transform("head", "mri")
    )
    mne.write_trans(meg / "all-trans.fif", mne.transforms.Transform("meg", "head"))
    return root


@pytest.fixture
def sample_import(monkeypatch, sample_source):
    """Stub large raw/calibration conversion while retaining real MRI/trans I/O."""
    monkeypatch.setattr(data_import.sample, "data_path", lambda: sample_source)
    monkeypatch.setattr(
        data_import.mne.io,
        "read_raw",
        lambda path: SimpleNamespace(info={"line_freq": None}),
    )

    def write_raw(*, bids_path, **kwargs):
        recording = bids_path.copy().update(suffix="meg", extension=".fif")
        recording.directory.mkdir(parents=True, exist_ok=True)
        recording.fpath.touch()
        recording.copy().update(extension=".json").fpath.write_text(
            "{}", encoding="utf-8"
        )

    monkeypatch.setattr(data_import, "write_raw_bids", write_raw)
    monkeypatch.setattr(data_import, "write_meg_calibration", Mock())
    monkeypatch.setattr(data_import, "write_meg_crosstalk", Mock())
    landmarks = mne.channels.make_dig_montage(
        lpa=[0.0, 1.0, 0.0],
        nasion=[1.0, 0.0, 0.0],
        rpa=[0.0, -1.0, 0.0],
        coord_frame="mri_voxel",
    )
    getter = Mock(return_value=landmarks)
    monkeypatch.setattr(data_import, "get_anat_landmarks", getter)
    return getter


@pytest.mark.parametrize("nested", [False, True])
def test_sample_import_exposes_anatomy_and_associated_outputs(
    ct, sample_source, sample_import, tmp_path, nested
):
    root = tmp_path / "sample-bids"
    freesurfer = root / "derivatives" / "freesurfer"
    if nested:
        freesurfer /= "subjects"
        freesurfer.mkdir(parents=True)
    data_import.load_sample_bids(root)
    ct.settings.set("bids_root", root)
    ct.settings.set("deriv_root", None)
    recording = BIDSPath(
        root=root,
        subject="01",
        session="01",
        task="audiovisual",
        run="1",
        datatype="meg",
        suffix="meg",
        extension=".fif",
    )
    subject = freesurfer / "sub-01"
    assert ct.subjects_dir == freesurfer
    assert ct.resolve_recording_subject(recording) == "sub-01"
    for folder in ("mri", "surf", "label", "bem"):
        assert (subject / folder / "contents.txt").read_text() == folder
    assert (subject / "bem" / "sub-01-head.fif").read_bytes() == b"scalp"
    assert (sample_source / "subjects" / "sample" / "bem" / "sample-head.fif").exists()
    assert not (subject / "bem" / "sample-head.fif").exists()
    image = root / "sub-01" / "ses-01" / "anat" / "sub-01_ses-01_T1w.nii.gz"
    assert nib.load(image).shape == (4, 4, 4)
    sidecar = image.with_name("sub-01_ses-01_T1w.json")
    assert "AnatomicalLandmarkCoordinates" in json.loads(sidecar.read_text())
    assert image.name in ct.get_datatype_items("anat")
    expected = trans_path(recording, root / "derivatives" / "mne-nodes")
    assert ct.find_recording_trans(recording) == expected
    transform = mne.read_trans(expected)
    assert transform["from"] == mne.io.constants.FIFF.FIFFV_COORD_HEAD
    assert transform["to"] == mne.io.constants.FIFF.FIFFV_COORD_MRI
    ct.input_selection_changed([recording.basename], "meg")
    unavailable = ct.input_output_availability()
    assert "subject" not in unavailable
    assert "trans" not in unavailable
    assert sample_import.call_args.kwargs["fs_subject"] == "sample"


def test_reimport_preserves_existing_anatomy_derivatives(
    tmp_path, sample_source, sample_import
):
    root = tmp_path / "sample-bids"
    data_import.load_sample_bids(str(root))
    subject_file = (
        root / "derivatives" / "freesurfer" / "sub-01" / "mri" / "contents.txt"
    )
    subject_file.write_text("user reconstruction", encoding="utf-8")
    anatomy = root / "sub-01" / "ses-01" / "anat" / "sub-01_ses-01_T1w.nii.gz"
    anatomy.write_bytes(b"existing anatomy")
    transform = next((root / "derivatives" / "mne-nodes").rglob("*_trans.fif"))
    transform.write_bytes(b"existing transformation")
    sample_import.reset_mock()
    data_import.load_sample_bids(root)
    assert subject_file.read_text() == "user reconstruction"
    assert anatomy.read_bytes() == b"existing anatomy"
    assert transform.read_bytes() == b"existing transformation"
    sample_import.assert_not_called()


@pytest.mark.parametrize("missing", ["transform", "image", "reconstruction"])
def test_converted_sample_completeness(tmp_path, sample_import, missing):
    """Raw-only caches and caches missing either derivative need an upgrade."""
    root = tmp_path / "sample-bids"
    data_import.load_sample_bids(root)
    assert data_import.sample_bids_has_anatomy(root)
    paths = {
        "transform": next((root / "derivatives" / "mne-nodes").rglob("*_trans.fif")),
        "image": root / "sub-01" / "ses-01" / "anat" / "sub-01_ses-01_T1w.nii.gz",
        "reconstruction": (
            root / "derivatives" / "freesurfer" / "sub-01" / "label" / "contents.txt"
        ),
    }
    paths[missing].unlink()
    if missing == "reconstruction":
        paths[missing].parent.rmdir()
    assert not data_import.sample_bids_has_anatomy(root)


def test_failed_reconstruction_copy_is_not_published(
    tmp_path, sample_source, monkeypatch
):
    """A copy failure leaves no partial subject or staging directory."""
    root = tmp_path / "bids"
    recording = BIDSPath(root=root, subject="01", session="01", datatype="meg")

    def fail_copy(source, destination):
        destination.mkdir()
        (destination / "partial").touch()
        raise OSError("Copy failed")

    monkeypatch.setattr(data_import, "copytree", fail_copy)
    with pytest.raises(OSError, match="Copy failed"):
        data_import._copy_sample_anatomy(
            sample_source, recording, mne.create_info([], 1)
        )
    assert list((root / "derivatives" / "freesurfer").iterdir()) == []


@pytest.mark.parametrize(
    "action",
    [
        "import-same",
        "import-new",
        "button-same",
        "button-new",
        "menu-same",
        "menu-new",
        "controller-same",
        "welcome-same",
    ],
)
def test_clean_input_node_refresh_after_import_or_root_selection(
    settings, qtbot, tmp_path, sample_import, monkeypatch, action
):
    """Fresh settings and an empty pipeline must discover newly added anatomy."""
    from mne_nodes.backend.controller import Controller
    from mne_nodes.gui.main_window import MainWindow

    root = tmp_path / "raw-only"
    recording = BIDSPath(
        root=root,
        subject="01",
        session="01",
        task="audiovisual",
        run="1",
        datatype="meg",
        suffix="meg",
        extension=".fif",
    )
    recording.directory.mkdir(parents=True)
    recording.fpath.touch()
    (root / "dataset_description.json").write_text(
        '{"Name": "sample-dataset", "BIDSVersion": "1.7.0"}', encoding="utf-8"
    )
    assert settings.get("plugin_config") == {}
    assert settings.get("config_path") is None
    settings.set("bids_root", root)
    controller = Controller(settings=settings)
    controller.config_path = tmp_path / "clean_pipeline.json"
    window = MainWindow(controller)
    qtbot.addWidget(window)
    window.finalize_controller_setup()
    node = window.viewer.input_node
    metadata = node.output(port_name="info")
    assert "anat" not in [port.name for port in node.outputs]
    controller.input_selection_changed([recording.basename], "meg")
    target = tmp_path / "sample-bids" if action.endswith("-new") else root
    target.mkdir(exist_ok=True)
    if not action.startswith("import") and action != "welcome-same":
        data_import.load_sample_bids(target)
    monkeypatch.setattr(
        "mne_nodes.backend.controller.ask_user", lambda *args, **kwargs: True
    )
    monkeypatch.setattr(
        "mne_nodes.gui.main_window.get_user_input", lambda *args, **kwargs: target
    )
    monkeypatch.setattr(
        "mne_nodes.gui.node.input_node.get_user_input", lambda *args, **kwargs: target
    )
    if action.startswith("import"):
        window.add_sample_bids()  # Real blocking WorkerDialog, not a mocked factory.
    elif action.startswith("button"):
        node.input_widget.set_root()
    elif action.startswith("menu"):
        window.change_bids_root()
    elif action == "welcome-same":
        from mne_nodes.gui.welcome_tour import _ensure_welcome_sample

        _ensure_welcome_sample(controller, window)
    else:
        controller.bids_root = target
    assert controller.bids_root == target
    assert window.viewer.input_node is node
    assert node.output(port_name="info") is metadata
    tabs = node.input_widget.tab_widget
    tab_names = [tabs.tabText(index) for index in range(tabs.count())]
    assert tab_names.count("anat") == 1
    assert [port.name for port in node.outputs].count("anat") == 1
    assert "subject" not in tab_names
    assert "trans" not in tab_names
    anatomy = tabs.widget(tab_names.index("anat"))
    expected_name = "sub-01_ses-01_T1w.nii.gz"
    assert anatomy.model.index(0, 0).data() == expected_name
    assert not node.output(port_name="anat").isEnabled()
    anatomy.model.setData(
        anatomy.model.index(0, 0), Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole
    )
    assert controller.get("selected_inputs")["anat"] == [expected_name]
    assert node.output(port_name="anat").isEnabled()
    if target == root:
        assert controller.get("selected_inputs")["meg"] == [recording.basename]
    else:
        assert not controller.get("selected_inputs")["meg"]
    # Re-selecting and restoring the graph must retain one anatomy tab and port.
    controller.input_selection_changed([recording.basename], "meg")
    assert node.output(port_name="subject").isEnabled()
    assert node.output(port_name="trans").isEnabled()
    saved = window.viewer.to_dict()
    window.viewer.load_nodes(saved)
    restored = window.viewer.input_node
    assert restored.output(port_name="anat").isEnabled()
    tabs = restored.input_widget.tab_widget
    assert [tabs.tabText(index) for index in range(tabs.count())].count("anat") == 1


@pytest.mark.parametrize("missing", ["transform", "image", "reconstruction"])
def test_missing_sample_anatomy_is_reported_before_copy(
    tmp_path, sample_source, missing
):
    paths = {
        "transform": sample_source / "MEG" / "sample" / "sample_audvis_raw-trans.fif",
        "image": sample_source / "subjects" / "sample" / "mri" / "T1.mgz",
        "reconstruction": sample_source
        / "subjects"
        / "sample"
        / "label"
        / "contents.txt",
    }
    paths[missing].unlink()
    if missing == "reconstruction":
        paths[missing].parent.rmdir()
    root = tmp_path / "bids"
    recording = BIDSPath(root=root, subject="01", session="01", datatype="meg")
    with pytest.raises((ValueError, FileNotFoundError), match="sample"):
        data_import._copy_sample_anatomy(
            sample_source, recording, mne.create_info([], 1)
        )
    assert not (root / "derivatives" / "freesurfer" / "sub-01").exists()
