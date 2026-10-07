"""Check the installed package's entry point, modules and bundled assets."""

from importlib import import_module
from importlib.metadata import distribution
from importlib.resources import files
from importlib.util import find_spec

import pytest
from qtpy.QtGui import QPixmap


@pytest.mark.parametrize(
    "module",
    [
        "mne_nodes.__main__",
        "mne_nodes.gui.main_window",
        "mne_nodes.backend.controller",
        "mne_nodes.backend.code_generation",
        "mne_nodes.resources.example_plugin",
    ],
)
def test_installed_modules(module):
    """Application modules must import without adding the source tree to sys.path."""
    assert import_module(module) is not None


@pytest.mark.parametrize(
    "name",
    [
        "Welcome_pipeline.json",
        "example_plugin.py",
        "example_plugin_config.json",
        "mne_pipeline_icon_dark.png",
        "mne_pipeline_icon_light.png",
        "mne_pipeline_logo_evee_smaller.jpg",
        "wip_overview.png",
    ],
)
def test_packaged_resources(name):
    """All runtime assets must be available through the installed package."""
    assert (files("mne_nodes.resources") / name).is_file()


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_packaged_icons(qapp, theme):
    """Qt must be able to decode the installed application icons."""
    icon = files("mne_nodes.resources") / f"mne_pipeline_icon_{theme}.png"
    assert not QPixmap(str(icon)).isNull()


@pytest.mark.parametrize(
    "name", ["tests", "conftest", "development", "ui", "pipeline", "extra"]
)
def test_package_excludes_old_modules(name):
    """Test helpers, development tooling and renamed packages are not shipped."""
    assert find_spec(f"mne_nodes.{name}") is None


def test_gui_entry_point():
    """The public launch command must still target the installed main function."""
    entry_points = distribution("mne-nodes").entry_points
    entry = next(
        entry
        for entry in entry_points
        if entry.group == "gui_scripts" and entry.name == "mne_nodes"
    )
    assert entry.value == "mne_nodes.__main__:main"
    assert callable(entry.load())
