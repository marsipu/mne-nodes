"""Discovery, fitting and persistence of head-to-MRI coregistrations."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import mne
import numpy as np
from mne_bids import BIDSPath, get_bids_path_from_fname, read_raw_bids
from mne_bids.config import ALLOWED_DATATYPES

from mne_nodes.backend.execution import WorkerSignals
from mne_nodes.logger import logger

if TYPE_CHECKING:
    from mne_nodes.backend.controller import Controller


def identical_digitization(first: mne.Info, second: mne.Info) -> bool:
    """Compare all digitizer fields exactly; absent digitization never matches."""
    first_dig, second_dig = first["dig"], second["dig"]
    if not first_dig or not second_dig or len(first_dig) != len(second_dig):
        return False
    return all(
        a.keys() == b.keys() and all(np.array_equal(a[key], b[key]) for key in a)
        for a, b in zip(first_dig, second_dig)
    )


def trans_path(recording: BIDSPath, deriv_root: Path) -> Path:
    """Return a recording-specific MNE-BIDS derivative transformation path."""
    return (
        recording.copy()
        .update(
            root=deriv_root, suffix="trans", extension=".fif", split=None, check=False
        )
        .fpath
    )


@dataclass
class CoregRecording:
    """One raw recording and its digitization or discovery error."""

    bids_path: BIDSPath
    info: mne.Info | None
    error: str | None = None
    existing_trans: Path | None = None


@dataclass
class CoregGroup:
    """Recordings with identical digitization within one subject/session."""

    recordings: list[CoregRecording]

    @property
    def info(self) -> mne.Info:
        """Return the representative measurement info, requiring digitization."""
        info = self.recordings[0].info
        if info is None or not info["dig"]:
            raise ValueError("This recording has no usable digitization.")
        return info


_TRANS_ENTITIES = {
    "sub": "subject",
    "ses": "session",
    "task": "task",
    "acq": "acquisition",
    "run": "run",
    "proc": "processing",
    "rec": "recording",
    "space": "space",
}
# Entities that label a file without restricting the recordings it applies to.
_IGNORED_TRANS_ENTITIES = {"split", "desc"}


def _same_entity(key: str, candidate: str, value: object) -> bool:
    if value is None:
        return False
    value = str(value)
    if key == "run" and candidate.isdigit() and value.isdigit():
        return int(candidate) == int(value)
    return candidate == value


def _trans_matches(recording: BIDSPath, path: Path) -> bool:
    """Check whether a ``_trans.fif`` or legacy ``-trans.fif`` file applies."""
    stem = path.name.removesuffix(".fif")
    if not stem.endswith(("_trans", "-trans")):
        return False
    entities: dict[str, str] = {}
    for part in stem[: -len("_trans")].split("_"):
        key, sep, value = part.partition("-")
        if not sep or not value or key in entities:
            return False
        entities[key] = value
    if path.parent.name in ALLOWED_DATATYPES and (
        path.parent.name != recording.datatype
    ):
        return False
    if entities.get("ses") != recording.session:
        return False
    for key, value in entities.items():
        if key in _IGNORED_TRANS_ENTITIES:
            continue
        attribute = _TRANS_ENTITIES.get(key)
        if attribute is None or not _same_entity(
            key, value, getattr(recording, attribute)
        ):
            return False
    return "sub" in entities


def _trans_candidates(recording: BIDSPath, root: Path) -> list[Path]:
    """List matching transformations with bounded globs below one subject."""
    base = root / f"sub-{recording.subject}"
    if recording.session is not None:
        base = base / f"ses-{recording.session}"
    if not base.is_dir():
        return []
    files = [*base.glob("*trans.fif"), *base.glob("*/*trans.fif")]
    return sorted(path for path in files if _trans_matches(recording, path))


def find_trans(
    recording: BIDSPath, deriv_root: Path | None, other_roots: Sequence[Path] = ()
) -> Path | None:
    """Find a canonical or unambiguous less-specific session transformation.

    The configured derivatives root is searched first and takes priority. If it
    contains no match, the other derivative pipeline folders in ``other_roots``
    are searched; files from preceding software may use the legacy
    ``-trans.fif`` naming. Multiple applicable files raise ``ValueError``.
    """
    matches: list[Path] = []
    if deriv_root is not None:
        canonical = trans_path(recording, deriv_root)
        if canonical.is_file():
            return canonical
        matches = _trans_candidates(recording, deriv_root)
    if not matches:
        for root in other_roots:
            matches += _trans_candidates(recording, root)
    if len(matches) > 1:
        raise ValueError(
            f"Ambiguous transformations for {recording.basename}: "
            f"{[str(path) for path in matches]}"
        )
    return matches[0] if matches else None


def discover_coreg_groups(
    controller: "Controller", worker_signals: WorkerSignals
) -> list[CoregGroup]:
    """Read raw headers without preloading and group verified digitizations."""
    bids_root = controller.ensure_bids_root(interactive=False)
    deriv_root = controller.ensure_deriv_root(interactive=False)
    other_roots = controller.other_derivative_roots()
    paths = [
        get_bids_path_from_fname(name).update(root=bids_root)
        for datatype in controller.raw_types
        for name in controller.get_datatype_items(datatype)
    ]
    worker_signals.pgbar_max.emit(len(paths))
    groups: list[CoregGroup] = []
    for number, path in enumerate(paths, 1):
        if worker_signals.was_canceled:
            break
        worker_signals.pgbar_text.emit(f"Reading digitization: {path.basename}")
        info, error, existing = None, None, None
        try:
            existing = find_trans(path, deriv_root, other_roots)
            with read_raw_bids(path, extra_params={"preload": False}) as raw:
                info = raw.info.copy()
            if not info["dig"]:
                error = "No digitization points available."
        except (OSError, ValueError, RuntimeError) as exc:
            error = str(exc)
        if error:
            logger.warning(f"Coregistration: {path.basename}: {error}")
        recording = CoregRecording(path, info, error, existing)
        for group in groups:
            representative = group.recordings[0]
            other = representative.bids_path
            if (
                not error
                and not representative.error
                and info is not None
                and representative.info is not None
                and (path.subject, path.session) == (other.subject, other.session)
                and identical_digitization(info, representative.info)
            ):
                group.recordings.append(recording)
                break
        else:
            groups.append(CoregGroup([recording]))
        worker_signals.pgbar_n.emit(number)
    return groups


def save_group_trans(
    group: CoregGroup,
    trans: mne.transforms.Transform,
    deriv_root: Path,
    *,
    overwrite: bool = False,
) -> list[Path]:
    """Save a head-to-MRI transform for every recording in a verified group."""
    info = group.info
    if any(
        recording.info is None or not identical_digitization(info, recording.info)
        for recording in group.recordings
    ):
        raise ValueError(
            "Cannot share a transformation across different digitizations."
        )
    if (trans["from"], trans["to"]) != (
        mne.io.constants.FIFF.FIFFV_COORD_HEAD,
        mne.io.constants.FIFF.FIFFV_COORD_MRI,
    ):
        raise ValueError("Expected a head-to-MRI transformation.")
    paths = list(
        dict.fromkeys(trans_path(r.bids_path, deriv_root) for r in group.recordings)
    )
    if not overwrite and any(path.exists() for path in paths):
        raise FileExistsError(
            "Transformations already exist; confirm replacement first."
        )
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        mne.write_trans(path, trans, overwrite=overwrite)
    for recording in group.recordings:
        recording.existing_trans = trans_path(recording.bids_path, deriv_root)
    return paths


def automatic_coregistration(
    group: CoregGroup,
    subject: str,
    subjects_dir: Path,
    deriv_root: Path,
    worker_signals: WorkerSignals,
    *,
    overwrite: bool = False,
) -> str:
    """Fit fiducials and ICP using MNE's automated coregistration recipe."""
    worker_signals.pgbar_max.emit(4)
    worker_signals.pgbar_text.emit("Initializing MRI surface and fiducials")
    coreg = mne.coreg.Coregistration(
        group.info, subject, subjects_dir=subjects_dir, fiducials="estimated"
    )
    worker_signals.pgbar_n.emit(1)
    if worker_signals.was_canceled:
        return "Coregistration canceled; no transformations saved."
    worker_signals.pgbar_text.emit("Fitting fiducials")
    coreg.fit_fiducials(verbose=True)
    worker_signals.pgbar_n.emit(2)
    if worker_signals.was_canceled:
        return "Coregistration canceled; no transformations saved."
    worker_signals.pgbar_text.emit("Initial ICP fit (6 iterations)")
    coreg.fit_icp(n_iterations=6, nasion_weight=2.0, verbose=True)
    coreg.omit_head_shape_points(distance=0.005)
    worker_signals.pgbar_n.emit(3)
    if worker_signals.was_canceled:
        return "Coregistration canceled; no transformations saved."
    worker_signals.pgbar_text.emit("Final ICP fit (20 iterations)")
    coreg.fit_icp(n_iterations=20, nasion_weight=10.0, verbose=True)
    distances = np.asarray(coreg.compute_dig_mri_distances()) * 1000
    if not distances.size or not np.isfinite(distances).all():
        raise ValueError("Coregistration produced no finite digitization distances.")
    if worker_signals.was_canceled:
        return "Coregistration canceled; no transformations saved."
    paths = save_group_trans(group, coreg.trans, deriv_root, overwrite=overwrite)
    worker_signals.pgbar_n.emit(4)
    return (
        f"Saved {len(paths)} transformation(s). Head-to-MRI distances "
        f"(mean/min/max): {distances.mean():.2f} / {distances.min():.2f} / "
        f"{distances.max():.2f} mm. Inspect alignment in the manual GUI."
    )
