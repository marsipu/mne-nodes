"""Import existing FreeSurfer reconstructions into a BIDS dataset."""

import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from mne_nodes.backend.execution import WorkerSignals


def is_freesurfer_subject(path: Path) -> bool:
    """Return whether a folder has the subject structure used by MNE-Nodes."""
    return all((path / name).is_dir() for name in ("mri", "surf", "label"))


def find_freesurfer_subjects(source: Path) -> list[Path]:
    """List subject folders directly inside an existing subjects directory."""
    if not source.is_dir():
        raise NotADirectoryError(
            f"FreeSurfer source directory does not exist: {source}"
        )
    return sorted(
        (path for path in source.iterdir() if is_freesurfer_subject(path)),
        key=lambda path: path.name,
    )


def import_freesurfer_subjects(
    sources: list[Path], destination: Path, worker_signals: WorkerSignals
) -> list[Path]:
    """Copy subjects without overwriting existing data or exposing partial subjects.

    Each subject is staged inside the destination filesystem before being renamed.
    Cancellation takes effect between subjects. Completed subjects are retained if
    a later copy fails; the failed subject's temporary copy is cleaned up.
    """
    if not sources:
        raise ValueError("Select at least one FreeSurfer subject to import.")
    destination = destination.resolve()
    targets = {destination / source.name for source in sources}
    if len(targets) != len(sources):
        raise ValueError("Selected subjects must have unique folder names.")
    for source in sources:
        if not is_freesurfer_subject(source):
            raise ValueError(f"Expected mri, surf and label directories in {source}.")
        resolved = source.resolve()
        if destination.is_relative_to(resolved) or resolved.is_relative_to(destination):
            raise ValueError(f"Source and destination must not overlap: {source}.")
        target = destination / source.name
        if target.exists() or target.is_symlink():
            raise FileExistsError(
                f"Subject already exists: {target}. No existing subjects were replaced."
            )
    destination.mkdir(parents=True, exist_ok=True)
    worker_signals.pgbar_max.emit(len(sources))
    imported = []
    for number, source in enumerate(sources, 1):
        if worker_signals.was_canceled:
            break
        worker_signals.pgbar_text.emit(f"Copying FreeSurfer subject: {source.name}")
        with TemporaryDirectory(
            prefix=".mne-nodes-import-", dir=destination
        ) as staging:
            staged = Path(staging) / source.name
            shutil.copytree(source, staged)
            # Do not publish an incomplete or canceled subject as a usable import.
            if worker_signals.was_canceled:
                break
            target = destination / source.name
            if target.exists() or target.is_symlink():
                raise FileExistsError(f"Subject appeared during import: {target}.")
            staged.rename(target)
        imported.append(target)
        worker_signals.pgbar_n.emit(number)
    return imported
