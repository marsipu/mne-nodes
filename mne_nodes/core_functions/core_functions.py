"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""


def bandpass_filter(raw, l_freq: float | None = None, h_freq: float | None = None):
    """Filter raw data."""
    raw.filter(l_freq=l_freq, h_freq=h_freq)

    return raw
