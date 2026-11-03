"""Check the installed package's entry point, modules and bundled assets."""

from importlib import import_module
from importlib.metadata import distribution
from importlib.resources import files
from importlib.util import find_spec

MODULES = (
    "mne_nodes.__main__",
    "mne_nodes.gui.main_window",
    "mne_nodes.backend.controller",
    "mne_nodes.backend.code_generation",
    "mne_nodes.resources.example_plugin",
)
RESOURCES = (
    "Welcome_pipeline.json",
    "example_plugin.py",
    "example_plugin_config.json",
    "mne_pipeline_icon_dark.png",
    "mne_pipeline_icon_light.png",
    "mne_pipeline_logo_evee_smaller.jpg",
    "wip_overview.png",
)
EXCLUDED = ("tests", "conftest", "development", "ui", "pipeline", "extra")


def test_package_contents():
    """Modules and assets are importable, old or development modules are not."""
    for module in MODULES:
        assert import_module(module) is not None, module
    for name in RESOURCES:
        assert (files("mne_nodes.resources") / name).is_file(), name
    for name in EXCLUDED:
        assert find_spec(f"mne_nodes.{name}") is None, name


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
