"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import mne
from mne.datasets import sample

from mne_bids import (
    BIDSPath,
    make_dataset_description,
    write_meg_calibration,
    write_meg_crosstalk,
    write_raw_bids,
)


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


def load_sample_bids(bids_root):
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
        name=task,
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
