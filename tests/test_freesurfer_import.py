"""Tests for safe dataset-local FreeSurfer imports and their Qt entry points."""

from pathlib import Path
from unittest.mock import Mock

import pytest
from qtpy.QtCore import Qt
from qtpy.QtWidgets import QMenu

from mne_nodes.backend import freesurfer
from mne_nodes.backend.execution import WorkerSignals
from mne_nodes.gui.freesurfer_widgets import FreeSurferImportDialog


def make_subject(root: Path, name: str = "sub-01") -> Path:
    """Create a small subject tree with representative additional contents."""
    subject = root / name
    for folder in ("mri", "surf", "label", "bem"):
        (subject / folder).mkdir(parents=True)
        (subject / folder / "test.txt").write_text(folder, encoding="utf-8")
    return subject


def test_subject_discovery(tmp_path):
    """Only direct children with all three required directories are offered."""
    source = tmp_path / "external"
    second = make_subject(source, "sub-02")
    first = make_subject(source)
    (source / "incomplete" / "mri").mkdir(parents=True)
    (source / "notes.txt").touch()
    assert freesurfer.find_freesurfer_subjects(source) == [first, second]
    with pytest.raises(NotADirectoryError):
        freesurfer.find_freesurfer_subjects(tmp_path / "absent")


def test_copy_preserves_source_and_all_contents(ct, tmp_path):
    """Copies become discoverable dataset subjects without changing originals."""
    sources = [make_subject(tmp_path / "external", name) for name in ("01", "02")]
    destination = ct.ensure_subjects_dir()
    signals = WorkerSignals()
    progress = Mock()
    signals.pgbar_n.connect(progress)
    result = freesurfer.import_freesurfer_subjects(sources, destination, signals)
    assert result == [destination / "01", destination / "02"]
    assert ct.get_datatype_items("subject") == ["01", "02"]
    assert progress.call_args.args == (2,)
    for source, target in zip(sources, result):
        for folder in ("mri", "surf", "label", "bem"):
            assert (target / folder / "test.txt").read_bytes() == (
                source / folder / "test.txt"
            ).read_bytes()
        (target / "mri" / "test.txt").write_text("changed", encoding="utf-8")
        assert (source / "mri" / "test.txt").read_text(encoding="utf-8") == "mri"
    assert not list(destination.glob(".mne-nodes-import-*"))


def test_collision_preflight_copies_nothing(tmp_path):
    """A collision anywhere in a batch must not merge or replace subjects."""
    sources = [make_subject(tmp_path / "external", name) for name in ("01", "02")]
    destination = tmp_path / "destination"
    existing = make_subject(destination, "02")
    with pytest.raises(FileExistsError, match="already exists"):
        freesurfer.import_freesurfer_subjects(sources, destination, WorkerSignals())
    assert not (destination / "01").exists()
    assert (existing / "mri" / "test.txt").read_text(encoding="utf-8") == "mri"


@pytest.mark.parametrize("invalid", ["empty", "duplicate", "incomplete", "overlap"])
def test_invalid_imports(tmp_path, invalid):
    """Reject invalid input and recursive copies before writing anything."""
    first = make_subject(tmp_path / "external")
    destination = tmp_path / "destination"
    if invalid == "empty":
        sources = []
    elif invalid == "duplicate":
        sources = [first, make_subject(tmp_path / "other")]
    elif invalid == "incomplete":
        sources = [tmp_path / "absent"]
    else:
        sources = [first]
        destination = first / "nested"
    with pytest.raises(ValueError):
        freesurfer.import_freesurfer_subjects(sources, destination, WorkerSignals())
    assert not destination.exists()


def test_import_from_destination_is_rejected(tmp_path):
    """Selecting dataset subjects as external sources cannot recurse into itself."""
    source = make_subject(tmp_path)
    with pytest.raises(ValueError, match="overlap"):
        freesurfer.import_freesurfer_subjects([source], tmp_path, WorkerSignals())


@pytest.mark.parametrize("cancel_during_copy", [False, True])
def test_cancel_removes_staging(tmp_path, monkeypatch, cancel_during_copy):
    """Canceled copies never appear as reconstructed subjects."""
    source = make_subject(tmp_path / "external")
    destination = tmp_path / "destination"
    signals = WorkerSignals()
    signals.was_canceled = not cancel_during_copy
    original = freesurfer.shutil.copytree

    def copy_and_cancel(*args, **kwargs):
        result = original(*args, **kwargs)
        signals.was_canceled = True
        return result

    if cancel_during_copy:
        monkeypatch.setattr(freesurfer.shutil, "copytree", copy_and_cancel)
    result = freesurfer.import_freesurfer_subjects([source], destination, signals)
    assert result == []
    assert not list(destination.iterdir())
    assert source.exists()


def test_failed_copy_keeps_only_completed_subjects(tmp_path, monkeypatch):
    """A failed subject's partial files are removed and the error propagates."""
    sources = [make_subject(tmp_path / "external", name) for name in ("01", "02")]
    destination = tmp_path / "destination"
    original = freesurfer.shutil.copytree

    def fail_second(source, target, *args, **kwargs):
        if Path(source) == sources[1]:
            Path(target).mkdir()
            (Path(target) / "partial.txt").touch()
            raise OSError("Disk full")
        return original(source, target, *args, **kwargs)

    monkeypatch.setattr(freesurfer.shutil, "copytree", fail_second)
    with pytest.raises(OSError, match="Disk full"):
        freesurfer.import_freesurfer_subjects(sources, destination, WorkerSignals())
    assert sorted(path.name for path in destination.iterdir()) == ["01"]
    assert freesurfer.is_freesurfer_subject(destination / "01")
    assert all(source.exists() for source in sources)


@pytest.mark.parametrize("single", [False, True])
def test_dialog_source_options_and_real_worker(
    ct, qtbot, tmp_path, monkeypatch, single
):
    """Both source options dispatch actual copies through the progress dialog."""
    source_root = tmp_path / "external"
    subject = make_subject(source_root)
    make_subject(source_root, "sub-02")
    monkeypatch.setattr(
        "mne_nodes.gui.freesurfer_widgets.get_user_input",
        lambda *args, **kwargs: subject if single else source_root,
    )
    dialog = FreeSurferImportDialog(ct)
    qtbot.addWidget(dialog)
    assert not dialog.import_button.isEnabled()
    button = dialog.single_button if single else dialog.directory_button
    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
    assert dialog.checked == (["sub-01"] if single else ["sub-01", "sub-02"])
    if not single:
        dialog.subjects.clear_all()
        assert not dialog.import_button.isEnabled()
        dialog.checked.append("sub-02")
        dialog.subjects.content_changed()
        dialog._selection_changed()
    with qtbot.waitSignal(dialog.subjects_imported, timeout=10000):
        qtbot.mouseClick(dialog.import_button, Qt.MouseButton.LeftButton)
    assert ct.get_datatype_items("subject") == (["sub-01"] if single else ["sub-02"])
    assert not dialog.import_button.isEnabled()
    assert "Imported 1 of 1" in dialog.status.text()


def test_dialog_picker_cancel(ct, qtbot, monkeypatch):
    """Canceling a folder picker leaves the current selection untouched."""
    dialog = FreeSurferImportDialog(ct)
    qtbot.addWidget(dialog)
    monkeypatch.setattr(
        "mne_nodes.gui.freesurfer_widgets.get_user_input", lambda *args, **kwargs: None
    )
    dialog._choose_subject()
    assert dialog.sources == {}
    assert not dialog.import_button.isEnabled()


def test_dialog_collision_reports_error(ct, qtbot, tmp_path, monkeypatch):
    """Worker failures remain explicit and never become success-shaped results."""
    source = make_subject(tmp_path / "external")
    make_subject(ct.ensure_subjects_dir())
    dialog = FreeSurferImportDialog(ct)
    qtbot.addWidget(dialog)
    dialog.sources = {source.name: source}
    dialog.checked.append(source.name)
    errors = Mock()
    monkeypatch.setattr("mne_nodes.gui.freesurfer_widgets.ErrorDialog", errors)
    dialog._import()
    errors.assert_called_once()
    assert "Subject already exists" in str(errors.call_args.args[0][1])
    assert "Import failed" in dialog.status.text()
    assert dialog.checked == [source.name]
    assert ct.get_datatype_items("subject") == [source.name]


def test_dialog_partial_cancellation_keeps_remaining_selection(
    ct, qtbot, tmp_path, monkeypatch
):
    """Keep unimported subjects selected for retry and explain cancellation."""
    dialog = FreeSurferImportDialog(ct)
    qtbot.addWidget(dialog)
    first = make_subject(tmp_path / "external", "01")
    second = make_subject(tmp_path / "external", "02")
    dialog.sources = {"01": first, "02": second}
    dialog.checked.extend(dialog.sources)
    worker = Mock()
    worker.return_value = [ct.ensure_subjects_dir() / "01"]
    monkeypatch.setattr(
        "mne_nodes.gui.freesurfer_widgets.WorkerDialog", Mock(return_value=worker)
    )
    with qtbot.waitSignal(dialog.subjects_imported):
        dialog._import()
    assert "Import canceled. Imported 1 of 2" in dialog.status.text()
    assert dialog.checked == ["02"]
    assert dialog.import_button.isEnabled()


def test_dialog_invalid_subject_explains_requirements(ct, qtbot, tmp_path, monkeypatch):
    """A non-subject source shows the required folder structure to the user."""
    dialog = FreeSurferImportDialog(ct)
    qtbot.addWidget(dialog)
    monkeypatch.setattr(
        "mne_nodes.gui.freesurfer_widgets.get_user_input",
        lambda *args, **kwargs: tmp_path,
    )
    errors = Mock()
    monkeypatch.setattr("mne_nodes.backend.exception_handling.ErrorDialog", errors)
    dialog._choose_subject()
    errors.assert_called_once()
    assert "mri, surf and label" in str(errors.call_args.args[0][1])
    assert not dialog.import_button.isEnabled()


def test_bids_menu_import_entry(main_window, monkeypatch):
    """Expose imports outside coregistration and refresh dataset inputs afterward."""
    dialog = Mock()
    factory = Mock(return_value=dialog)
    monkeypatch.setattr("mne_nodes.gui.main_window.FreeSurferImportDialog", factory)
    menu = next(
        m for m in main_window.menuBar().findChildren(QMenu) if m.title() == "&BIDS"
    )
    action = next(
        a for a in menu.actions() if a.text() == "&Import FreeSurfer subjects..."
    )
    action.trigger()
    factory.assert_called_once_with(main_window.controller, main_window)
    dialog.subjects_imported.connect.assert_called_once_with(
        main_window._refresh_dataset_inputs
    )
    dialog.open.assert_called_once_with()


def test_coregistration_import_refresh(ct, qtbot, tmp_path, monkeypatch):
    """Imported subjects appear in coregistration without reopening the manager."""
    from mne_nodes.gui.coreg_widgets import CoregDialog

    dialog = CoregDialog(ct)
    qtbot.addWidget(dialog)
    importer = Mock()
    factory = Mock(return_value=importer)
    monkeypatch.setattr("mne_nodes.gui.coreg_widgets.FreeSurferImportDialog", factory)
    qtbot.mouseClick(dialog.import_button, Qt.MouseButton.LeftButton)
    factory.assert_called_once_with(ct, dialog)
    importer.subjects_imported.connect.assert_called_once_with(
        dialog._subjects_imported
    )
    source = make_subject(tmp_path / "external")
    freesurfer.import_freesurfer_subjects(
        [source], ct.ensure_subjects_dir(), WorkerSignals()
    )
    dialog._subjects_imported()
    assert dialog.mri_subject.findText("sub-01") >= 0
