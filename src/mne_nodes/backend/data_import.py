"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

from pathlib import Path
from shutil import copy2, copytree
from tempfile import TemporaryDirectory

import mne
from mne.datasets import sample
from mne_bids import (
    BIDSPath,
    get_anat_landmarks,
    make_dataset_description,
    write_anat,
    write_meg_calibration,
    write_meg_crosstalk,
    write_raw_bids,
)

from mne_nodes.backend.coregistration import trans_path
from mne_nodes.backend.freesurfer import is_freesurfer_subject

datasets = {
    "testing": {
        "io_mapping": {
            "raw": "sample_audvis_trunc_raw.fif",
            "erm": "sample_audvis_trunc_raw.fif",
            "events": "sample_audvis_trunc_raw-eve.fif",
            "evoked": "sample_audvis_trunc-ave.fif",
            "noise_cov": "sample_audvis_trunc-cov.fif",
            "trans": "sample_audvis_trunc-trans.fif",
            "forward": "sample_audvis_trunc-meg-eeg-oct-6-fwd.fif",
            "inverse": "sample_audvis_trunc-meg-eeg-oct-6-meg-inv.fif",
            "stcs": "sample_audvis_trunc-meg",
        },
        "load": mne.datasets.testing.data_path,
    },
    "sample": {
        "io_mapping": {
            "raw": "sample_audvis_raw.fif",
            "erm": "ernoise_raw.fif",
            "events": "sample_audvis_raw-eve.fif",
            "evoked": "sample_audvis-ave.fif",
            "noise_cov": "sample_audvis-cov.fif",
            "trans": "all-trans.fif",
            "forward": "sample_audvis-meg-eeg-oct-6-fwd.fif",
            "inverse": "sample_audvis-meg-eeg-oct-6-meg-eeg-inv.fif",
            "stcs": "sample_audvis-meg-eeg",
        },
        "load": mne.datasets.sample.data_path,
    },
}


def load_sample_bids(bids_root: str | Path) -> None:
    """Load the MNE sample data organized in BIDS format.
    Code modified from https://mne.tools/mne-bids/stable/auto_examples/convert_mne_sample.html."""
    # Load sample data
    print("Loading sample data...")
    data_path = sample.data_path()
    event_id = {
        "Auditory/Left": 1,
        "Auditory/Right": 2,
        "Visual/Left": 3,
        "Visual/Right": 4,
        "Smiley": 5,
        "Button": 32,
    }

    raw_fname = data_path / "MEG" / "sample" / "sample_audvis_raw.fif"
    er_fname = data_path / "MEG" / "sample" / "ernoise_raw.fif"  # empty room
    events_fname = data_path / "MEG" / "sample" / "sample_audvis_raw-eve.fif"

    raw = mne.io.read_raw(raw_fname)
    raw_er = mne.io.read_raw(er_fname)

    # specify power line frequency as required by BIDS
    raw.info["line_freq"] = 60
    raw_er.info["line_freq"] = 60

    task = "audiovisual"
    bids_path = BIDSPath(
        subject="01", session="01", task=task, run="1", datatype="meg", root=bids_root
    )
    print("Writing data to BIDS format...")
    write_raw_bids(
        raw=raw,
        bids_path=bids_path,
        events=events_fname,
        event_id=event_id,
        empty_room=raw_er,
        overwrite=True,
    )

    # Get the sidecar ``.json`` file
    sidecar_json_bids_path = bids_path.copy().update(suffix="meg", extension=".json")
    sidecar_json_content = sidecar_json_bids_path.fpath.read_text(encoding="utf-8-sig")
    print(sidecar_json_content)

    cal_fname = data_path / "SSS" / "sss_cal_mgh.dat"
    ct_fname = data_path / "SSS" / "ct_sparse_mgh.fif"

    write_meg_calibration(cal_fname, bids_path)
    write_meg_crosstalk(ct_fname, bids_path)
    _copy_sample_anatomy(data_path, bids_path, raw.info)

    how_to_acknowledge = """\
    If you reference this dataset in a publication, please acknowledge its \
    authors and cite MNE papers: A. Gramfort, M. Luessi, E. Larson, D. Engemann, \
    D. Strohmeier, C. Brodbeck, L. Parkkonen, M. Hämäläinen, \
    MNE software for processing MEG and EEG data, NeuroImage, Volume 86, \
    1 February 2014, Pages 446-460, ISSN 1053-8119 \
    and \
    A. Gramfort, M. Luessi, E. Larson, D. Engemann, D. Strohmeier, C. Brodbeck, \
    R. Goj, M. Jas, T. Brooks, L. Parkkonen, M. Hämäläinen, MEG and EEG data \
    analysis with MNE-Python, Frontiers in Neuroscience, Volume 7, 2013, \
    ISSN 1662-453X"""

    make_dataset_description(
        path=bids_path.root,
        name="sample-dataset",
        authors=["Alexandre Gramfort", "Matti Hämäläinen"],
        how_to_acknowledge=how_to_acknowledge,
        acknowledgements="""\
    Alexandre Gramfort, Mainak Jas, and Stefan Appelhoff prepared and updated the \
    data in BIDS format.""",
        data_license="CC0",
        ethics_approvals=["Human Subjects Division at the University of Washington"],
        funding=[
            "NIH 5R01EB009048",
            "NIH 1R01EB009048",
            "NIH R01EB006385",
            "NIH 1R01HD40712",
            "NIH 1R01NS44319",
            "NIH 2R01NS37462",
            "NIH P41EB015896",
            "ANR-11-IDEX-0003-02",
            "ERC-StG-263584",
            "ERC-StG-676943",
            "ANR-14-NEUC-0002-01",
        ],
        references_and_links=[
            "https://doi.org/10.1016/j.neuroimage.2014.02.017",
            "https://doi.org/10.3389/fnins.2013.00267",
            "https://mne.tools/stable/documentation/datasets.html#sample",
        ],
        doi="doi:10.18112/openneuro.ds000248.v1.2.4",
        overwrite=True,
    )
    print("Sample data successfully written to BIDS format.")


def _copy_sample_anatomy(data_path: Path, recording: BIDSPath, info: mne.Info) -> None:
    """Make the sample reconstruction, T1w image and transform discoverable."""
    source = data_path / "subjects" / "sample"
    transform = data_path / "MEG" / "sample" / "sample_audvis_raw-trans.fif"
    image = source / "mri" / "T1.mgz"
    if not is_freesurfer_subject(source):
        raise ValueError(
            f"The sample FreeSurfer reconstruction is incomplete: {source}"
        )
    for path in (image, transform):
        if not path.is_file():
            raise FileNotFoundError(f"Required sample anatomy file is missing: {path}")
    root = recording.root
    if root is None:
        raise ValueError("A BIDS root is required to import sample anatomy.")
    subjects_dir = root / "derivatives" / "freesurfer"
    if (subjects_dir / "subjects").is_dir():
        subjects_dir /= "subjects"
    subject = f"sub-{recording.subject}"
    destination = subjects_dir / subject
    if subjects_dir.resolve().is_relative_to(source.resolve()):
        raise ValueError("The sample import destination must not be inside its source.")
    if destination.exists():
        if not is_freesurfer_subject(destination):
            raise ValueError(
                f"Existing FreeSurfer subject is incomplete: {destination}"
            )
    else:
        print("Copying sample FreeSurfer reconstruction...")
        subjects_dir.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(
            prefix=".mne-nodes-import-", dir=subjects_dir
        ) as folder:
            staged = Path(folder) / subject
            copytree(source, staged)
            # MNE looks up scalp and BEM files using the FreeSurfer subject name.
            for path in (staged / "bem").rglob("sample-*"):
                if path.is_file():
                    path.rename(
                        path.with_name(path.name.replace("sample-", f"{subject}-", 1))
                    )
            staged.rename(destination)
    anatomy = recording.copy().update(
        datatype="anat", task=None, run=None, suffix="T1w", extension=".nii.gz"
    )
    if not anatomy.fpath.exists():
        print("Writing sample T1w anatomy...")
        landmarks = get_anat_landmarks(
            image,
            info,
            transform,
            fs_subject="sample",
            fs_subjects_dir=data_path / "subjects",
        )
        write_anat(image, anatomy, landmarks=landmarks, overwrite=False)
    destination_trans = trans_path(recording, root / "derivatives" / "mne-nodes")
    if not destination_trans.exists():
        destination_trans.parent.mkdir(parents=True, exist_ok=True)
        copy2(transform, destination_trans)


def sample_bids_has_anatomy(bids_root: Path) -> bool:
    """Check whether a converted sample has its discoverable auxiliary data."""
    recording = BIDSPath(
        root=bids_root,
        subject="01",
        session="01",
        task="audiovisual",
        run="1",
        datatype="meg",
    )
    subjects_dir = bids_root / "derivatives" / "freesurfer"
    if (subjects_dir / "subjects").is_dir():
        subjects_dir /= "subjects"
    anatomy = recording.copy().update(
        datatype="anat", task=None, run=None, suffix="T1w", extension=".nii.gz"
    )
    return (
        is_freesurfer_subject(subjects_dir / "sub-01")
        and anatomy.fpath.is_file()
        and trans_path(recording, bids_root / "derivatives" / "mne-nodes").is_file()
    )
