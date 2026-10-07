def example_filter(raw, highpass=1, lowpass=30):
    """
    This is an example function, that processes the raw-data of a the mne-sample-dataset.
    """
    raw = raw.filter(highpass, lowpass)
    return raw
