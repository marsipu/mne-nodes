"""Tests for safe dataset-local FreeSurfer subject discovery and imports."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from mne_nodes.backend import freesurfer
from mne_nodes.backend.execution import WorkerSignals


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


@pytest.mark.parametrize("nested", [False, True])
def test_copy_preserves_source_and_all_contents(ct, tmp_path, nested):
    """Copies become discoverable dataset subjects without changing originals."""
    sources = [make_subject(tmp_path / "external", name) for name in ("01", "02")]
    expected = ct.bids_root / "derivatives" / "freesurfer"
    if nested:
        expected /= "subjects"
        expected.mkdir(parents=True)
    destination = ct.ensure_subjects_dir()
    assert destination == expected
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


def test_nested_subjects_directory(ct):
    """Prefer nested reconstructions and pass their parent to MNE functions."""
    root = ct.bids_root / "derivatives" / "freesurfer"
    make_subject(root, "direct")
    nested = root / "subjects"
    make_subject(nested)
    make_subject(nested, "fsaverage")
    (nested / "morph-maps").mkdir()

    assert ct.subjects_dir == nested
    assert ct.ensure_subjects_dir(False) == nested
    assert ct.get_datatype_items("subject") == ["fsaverage", "sub-01"]
    assert ct.load_subject("sub-01") == "sub-01"
    assert ct.parameter("subjects_dir", "unused") == nested
    assert "subject" in ct.get_datatypes()
    assert "subject" not in ct.get_all_datatype_items()
    assert not (root / "sub-01").exists()


@pytest.mark.parametrize(
    "invalid",
    ["empty", "duplicate", "incomplete", "overlap", "from_destination", "collision"],
)
def test_invalid_imports_write_nothing(tmp_path, invalid):
    """Reject invalid, recursive or colliding imports before writing anything."""
    first = make_subject(tmp_path / "external")
    destination = tmp_path / "destination"
    error = ValueError
    if invalid == "empty":
        sources = []
    elif invalid == "duplicate":
        sources = [first, make_subject(tmp_path / "other")]
    elif invalid == "incomplete":
        sources = [tmp_path / "absent"]
    elif invalid == "overlap":
        sources = [first]
        destination = first / "nested"
    elif invalid == "from_destination":
        sources = [first]
        destination = first.parent
    else:
        sources = [first, make_subject(tmp_path / "external", "02")]
        make_subject(destination, "02")
        error = FileExistsError
    before = sorted(tmp_path.rglob("*"))
    with pytest.raises(error):
        freesurfer.import_freesurfer_subjects(sources, destination, WorkerSignals())
    assert sorted(tmp_path.rglob("*")) == before
    assert (first / "mri" / "test.txt").read_text(encoding="utf-8") == "mri"


@pytest.mark.parametrize("outcome", ["cancel_before", "cancel_during", "failure"])
def test_cancel_or_failure_leaves_consistent_state(tmp_path, monkeypatch, outcome):
    """Canceled or failed copies never appear as (partial) subjects."""
    sources = [make_subject(tmp_path / "external", name) for name in ("01", "02")]
    destination = tmp_path / "destination"
    signals = WorkerSignals()
    signals.was_canceled = outcome == "cancel_before"
    original = freesurfer.shutil.copytree

    def copy_and_cancel(*args, **kwargs):
        result = original(*args, **kwargs)
        signals.was_canceled = True
        return result

    def fail_second(source, target, *args, **kwargs):
        if Path(source) == sources[1]:
            Path(target).mkdir()
            (Path(target) / "partial.txt").touch()
            raise OSError("Disk full")
        return original(source, target, *args, **kwargs)

    if outcome == "failure":
        monkeypatch.setattr(freesurfer.shutil, "copytree", fail_second)
        with pytest.raises(OSError, match="Disk full"):
            freesurfer.import_freesurfer_subjects(sources, destination, signals)
        assert sorted(path.name for path in destination.iterdir()) == ["01"]
        assert freesurfer.is_freesurfer_subject(destination / "01")
    else:
        if outcome == "cancel_during":
            monkeypatch.setattr(freesurfer.shutil, "copytree", copy_and_cancel)
        result = freesurfer.import_freesurfer_subjects(
            sources[:1], destination, signals
        )
        assert result == []
        assert not list(destination.iterdir())
    assert all(source.exists() for source in sources)
