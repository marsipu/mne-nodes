"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import mne


def filter_bandpass(
    raw,
    l_freq: float | None = None,
    h_freq: float | None = None,
    n_jobs: int | str | None = -1,
):
    """Filter raw data."""
    if not raw.preload:
        raw.load_data()
    raw.filter(l_freq=l_freq, h_freq=h_freq, n_jobs=n_jobs)

    return raw


def create_epochs(
    raw,
    events=None,
    event_id: dict | None = None,
    t_epoch: tuple[float, float] = (0, 1),
    baseline: tuple[float, float] | None = None,
):
    # ToDo: Problem what if events as input is not always necessary? Rethink logic of function-recognition?
    if events is None:
        events, event_id = mne.events_from_annotations(raw)

    epochs = mne.Epochs(
        raw=raw,
        events=events,
        event_id=event_id,
        tmin=t_epoch[0],
        tmax=t_epoch[1],
        baseline=baseline,
    )
    return epochs


def create_evokeds(epochs, conditions: list = None):
    if conditions is not None:
        evokeds = []
        for cond in conditions:
            evoked = epochs[cond].average()
            evokeds.append(evoked)
    else:
        evokeds = epochs.average()

    return evokeds


def plot_evokeds(evokeds):
    evokeds.plot()


def grand_average_evokeds(
    evokeds, interpolate_bads: bool = True, drop_bads: bool = True
):
    ga_evokeds = mne.grand_average(
        [evokeds], interpolate_bads=interpolate_bads, drop_bads=drop_bads
    )

    return ga_evokeds
