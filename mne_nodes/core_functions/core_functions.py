"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import mne
import numpy as np


def filter_bandpass(
    raw,
    l_freq: float | None = None,
    h_freq: float | None = None,
    n_jobs: int | str | None = -1,
):
    """Filter raw data."""
    raw.filter(l_freq=l_freq, h_freq=h_freq, n_jobs=n_jobs)

    return raw


def create_epochs(raw, events: np.array = None, event_id: dict | None = None):
    # ToDo: Problem what if events as input is not always necessary? Rethink logic of function-recognition?
    if events is None:
        events, event_id = mne.events_from_annotations(raw)
