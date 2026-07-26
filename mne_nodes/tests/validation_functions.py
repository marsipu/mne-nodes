"""Validation pipeline functions used by GUI/node checks.

These functions are intentionally lightweight and compatible with the tiny BIDS
fixture data under mne_nodes/tests/tiny_bids.
"""

from __future__ import annotations

import mne


def test_filter(
    raw,
    l_freq: float | None = None,
    h_freq: float | None = None,
    n_jobs: int | str | None = -1,
):
    """Filter raw data with optional bounds."""
    if not raw.preload:
        raw.load_data()
    raw.filter(l_freq=l_freq, h_freq=h_freq, n_jobs=n_jobs)
    return raw


def test_epochs(
    raw,
    events=None,
    event_id: dict | None = None,
    t_epoch: tuple[float, float] = (0, 1),
    baseline: tuple[float, float] | None = None,
):
    """Create epochs from raw and optional events."""
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


def test_evokeds(epochs, conditions=None):
    """Create one or more evoked objects from epochs."""
    if conditions is not None:
        evokeds = []
        for cond in conditions:
            evokeds.append(epochs[cond].average())
        return evokeds
    return epochs.average()


def test_plot_evokeds(evokeds):
    """Plot evokeds without forcing GUI display in test runs."""
    if isinstance(evokeds, list):
        mne.viz.plot_compare_evokeds(evokeds, show=False)
    else:
        evokeds.plot(show=False)
