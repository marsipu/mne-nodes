"""Read-only dataset inventory and recording-to-auxiliary associations."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from mne_bids import get_bids_path_from_fname

from mne_nodes.backend.coregistration import find_trans
from mne_nodes.backend.execution import WorkerSignals

if TYPE_CHECKING:
    from mne_nodes.backend.controller import Controller


@dataclass(frozen=True)
class DataAvailability:
    """An availability state and its explanation, independent of presentation."""

    state: Literal["present", "missing", "error", "not_applicable"]
    description: str


@dataclass
class DataOverview:
    """Recording rows and auxiliary paths, including unassociated dataset files."""

    recordings: list[dict[str, str | DataAvailability]]
    inventory: dict[str, list[str]]


def discover_data_overview(
    controller: "Controller", worker_signals: WorkerSignals | None = None
) -> DataOverview:
    """Inspect associations, reporting discovery and per-recording progress."""
    if worker_signals is not None:
        worker_signals.pgbar_max.emit(0)
        worker_signals.pgbar_text.emit("Discovering anatomy and auxiliary data...")
    ct = controller
    root = ct.ensure_bids_root(interactive=False)
    anatomy = ct._get_datatype_candidates("anat")
    anatomy_sessions = {(path.subject, path.session) for path in anatomy}
    subject_cache: dict[tuple[str | None, str | None], DataAvailability] = {}
    subject_mappings = ct.get("coreg_subjects", {})
    subjects_dir = ct.subjects_dir
    deriv_root = ct.deriv_root
    other_roots = ct.other_derivative_roots()
    inventory = {
        "Anatomy": [str(path.fpath) for path in anatomy],
        "FreeSurfer": [
            str(subjects_dir / subject) for subject in ct.get_datatype_items("subject")
        ]
        if subjects_dir is not None
        else [],
        "Empty-room": [
            str(get_bids_path_from_fname(name).update(root=root).fpath)
            for name in ct.get_datatype_items("emptyroom")
        ],
    }
    recording_names = {
        datatype: ct.get_datatype_items(datatype) for datatype in ct.raw_types
    }
    total = sum(len(names) for names in recording_names.values())
    if worker_signals is not None:
        worker_signals.pgbar_max.emit(max(1, total))
        worker_signals.pgbar_n.emit(0)
    rows = []
    for datatype, names in recording_names.items():
        for name in names:
            if worker_signals is not None:
                worker_signals.pgbar_text.emit(
                    f"Checking recording {len(rows) + 1}/{total}: {name}"
                )
            recording = get_bids_path_from_fname(name).update(root=root)
            row: dict[str, str | DataAvailability] = {"Recording": recording.basename}
            has_anatomy = any(
                (recording.subject, session) in anatomy_sessions
                for session in (None, recording.session)
            )
            row["Anatomy candidates"] = DataAvailability(
                "present" if has_anatomy else "missing",
                "Anatomical candidate found (subject/session match only)."
                if has_anatomy
                else "No anatomical candidate found.",
            )
            subject_key = (recording.subject, subject_mappings.get(recording.basename))
            if subject_key not in subject_cache:
                try:
                    subject = ct.resolve_recording_subject(recording)
                    subject_cache[subject_key] = DataAvailability(
                        "present", f"FreeSurfer subject: {subject}"
                    )
                except FileNotFoundError:
                    subject_cache[subject_key] = DataAvailability(
                        "missing", "No matching FreeSurfer subject."
                    )
            row["FreeSurfer subject"] = subject_cache[subject_key]
            try:
                trans = find_trans(recording, deriv_root, other_roots)
                row["Transform"] = DataAvailability(
                    "present" if trans else "missing",
                    "Head-to-MRI transformation found."
                    if trans
                    else "No head-to-MRI transformation found.",
                )
            except (OSError, ValueError, RuntimeError) as error:
                row["Transform"] = DataAvailability("error", str(error))
            if datatype == "meg":
                try:
                    empty_room = ct.resolve_empty_room(recording)
                    row["Empty-room"] = DataAvailability(
                        "present", f"Associated empty-room: {empty_room.basename}"
                    )
                except FileNotFoundError as error:
                    row["Empty-room"] = DataAvailability("missing", str(error))
                except (OSError, ValueError, RuntimeError) as error:
                    row["Empty-room"] = DataAvailability("error", str(error))
            else:
                row["Empty-room"] = DataAvailability(
                    "not_applicable", "Not applicable (MEG only)."
                )
            rows.append(row)
            if worker_signals is not None:
                worker_signals.pgbar_n.emit(len(rows))
    if worker_signals is not None:
        if total == 0:
            worker_signals.pgbar_n.emit(1)
        worker_signals.pgbar_text.emit(f"Scan complete: {total} recordings.")
    return DataOverview(rows, inventory)
