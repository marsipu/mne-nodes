"""Illustrative functions imported into the documentation screenshot project.

The sensor positions, spherical model and covariance are for illustration only
and are not a scientifically validated source analysis.
"""

import mne


def prepare_eeg(raw, resample=200):
    """Use synthetic sensor positions for this source-analysis example."""
    channels = ["Fp1", "Fp2", "F3", "F4", "C3", "C4", "P3", "P4"]
    raw = raw.copy().load_data().pick(channels)
    positions = {
        "Fp1": (-0.03, 0.075, 0.03),
        "Fp2": (0.03, 0.075, 0.03),
        "F3": (-0.04, 0.04, 0.07),
        "F4": (0.04, 0.04, 0.07),
        "C3": (-0.06, 0.0, 0.07),
        "C4": (0.06, 0.0, 0.07),
        "P3": (-0.04, -0.04, 0.07),
        "P4": (0.04, -0.04, 0.07),
    }
    montage = mne.channels.make_dig_montage(ch_pos=positions, coord_frame="head")
    raw.set_montage(montage)
    raw.set_eeg_reference("average", projection=True)
    raw.resample(resample)
    return raw


def create_epochs(raw, duration=0.4):
    """Create fixed-length epochs for an interface demonstration."""
    epochs = mne.make_fixed_length_epochs(raw, duration=duration, preload=True)
    return epochs


def average_epochs(epochs, picks="eeg"):
    """Average epochs for an interface demonstration."""
    evoked = epochs.average(picks=picks)
    return evoked


def noise_covariance(epochs, method="empirical"):
    """Estimate covariance from the same short example recording."""
    cov = mne.compute_covariance(epochs, method=method)
    return cov


def spherical_forward(raw, spacing=40.0):
    """Create a coarse spherical model; it is not an anatomical fit."""
    sphere = mne.make_sphere_model(r0=(0, 0, 0), head_radius=0.09)
    src = mne.setup_volume_source_space(
        subject=None, pos=spacing, sphere=(0, 0, 0, 0.08), exclude=20.0, verbose=False
    )
    forward = mne.make_forward_solution(
        raw.info, trans=None, src=src, bem=sphere, eeg=True, meg=False, verbose=False
    )
    return forward


def estimate_sources(evoked, cov, forward, snr=3.0):
    """Compute an illustrative minimum-norm source estimate."""
    inverse = mne.minimum_norm.make_inverse_operator(
        evoked.info, forward, cov, loose=1.0, depth=None
    )
    stc = mne.minimum_norm.apply_inverse(
        evoked, inverse, lambda2=1.0 / snr**2, method="MNE"
    )
    return stc
