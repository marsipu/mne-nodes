"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import mne

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
