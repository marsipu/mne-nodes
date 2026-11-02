from pathlib import Path

from mne_nodes.gui.welcome_tour import start_welcome_tour


def test_welcome_tour_runs_through_all_steps(main_window, monkeypatch):
    """The tour shows every step and restores the user's state when finished."""
    ct = main_window.controller
    previous_plugins = ct.plugins.copy()
    previous_functions = ct.function_meta.copy()
    previous_settings = ct.settings._load()
    monkeypatch.setattr(
        "mne_nodes.gui.welcome_tour.ask_user", lambda *args, **kwargs: True
    )
    monkeypatch.setattr(
        "mne_nodes.gui.welcome_tour._ensure_welcome_sample",
        lambda *args, **kwargs: None,
    )
    tour = start_welcome_tour(ct, main_window)
    assert tour is not None
    directory = Path(tour.demo_directory.name)
    try:
        for index in range(len(tour.steps)):
            tour.show_step(index)
            assert tour.index == index
    finally:
        tour.finish(notify=False)
    assert tour._finished
    assert not directory.exists()
    assert ct.plugins == previous_plugins
    assert ct.function_meta == previous_functions
    assert ct.settings._load() == previous_settings
