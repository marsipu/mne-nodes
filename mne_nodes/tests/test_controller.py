"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from mne_nodes import _widgets
from mne_nodes.pipeline.controller import Controller
from mne_nodes.pipeline.io import TypedJSONEncoder
from mne_nodes.pipeline.pipeline_utils import change_file_section


def test_init(ct):
    assert ct.name == "test"
    # Test renaming the controller
    ct.name = "test2"
    assert ct.name == "test2", "Controller name should be updated to 'test2'"
    # Test persistence for reloading
    config_path = ct.config_path
    ct.flush()
    controller2 = Controller(config_path=config_path)
    assert controller2.name == "test2"
    # Test parameter set
    ct.set_parameter("param1", 42, "test_func1")
    assert ct.parameter("param1", "test_func1") == 42, (
        "Parameter 'param1' should be set to 42"
    )


def test_plugin_import(tmp_path, ct, test_plugin_config, test_script):
    # ToDo Next: Fix get_function_code
    # Assert basic plugins are imported
    assert "validation_functions" in ct.plugins

    # Add a custom plugin
    ct.load_plugin_path(test_plugin_config)
    assert "test_module" in ct.plugins, "Custom plugin should be imported"

    # Test custom plugin reload
    original_func = ct.plugins["test_module"].test_func1
    assert original_func(2) == 4, "Custom function should return correct value"

    # Modify the module source code
    _func1_code, start, end = ct.get_function_code("test_func1")

    new_test_code = "def test_func1(a):\n    return a ** 3\n"
    change_file_section(test_script, (start, end), new_test_code)

    # Reload the plugins
    ct.reload_plugins()

    # Get a new reference to the function
    new_func = ct.plugins["test_module"].test_func1
    print(f"New function: {new_func} at {id(new_func)}")
    assert new_func(2) == 8, "New function reference should return updated value"

    # Test insertion


def test_config_change(tmp_path, ct, monkeypatch):
    old_config_path = ct.config_path
    # Check controller change with other options
    new_config_path = tmp_path / "new_config.json"
    test_dict = {
        "name": "test2",
        "parameters": {"test_func1": {"param_a": 1, "param_b": 2}},
    }
    with open(new_config_path, "w") as f:
        json.dump(test_dict, f, indent=4, cls=TypedJSONEncoder)
    # Simulate input to new config-path
    # Create a new config-file? Use existing!
    monkeypatch.setattr(
        "mne_nodes.pipeline.controller.ask_user_custom", lambda *a, **k: False
    )
    # Path to existing config-file
    monkeypatch.setattr(
        "mne_nodes.pipeline.controller.get_user_input", lambda *a, **k: new_config_path
    )
    ct.config_path = None
    assert ct.name == "test2", "Controller name should be updated to 'test2'"
    assert ct.parameter("param_a", "test_func1") == 1, (
        "New parameter should be loaded from config"
    )
    # Add parameters for test
    ct.set_parameter("new_param", 42, "test_func1")
    assert ct.parameter("new_param", "test_func1") == 42, "New parameter should be set"
    ct.flush()
    # Change back to other controller
    ct.config_path = old_config_path
    assert ct.name == "test", "Controller name should be reverted to 'test'"
    assert "new_param" not in ct.get("parameters"), (
        "Parameters should be reverted on config change"
    )
    # Change again to new config
    ct.config_path = new_config_path
    assert ct.name == "test2", "Controller name should be updated to 'test2'"
    assert ct.parameter("param_b", "test_func1") == 2, "New parameter should be set"
    assert ct.parameter("new_param", "test_func1") == 42, (
        "New parameter should persist after config reload"
    )


def test_getters_noninteractive(settings):
    controller = Controller(settings=settings)

    assert controller.config_path is None
    assert controller.bids_root is None
    assert controller.deriv_root is None
    assert controller.plot_root is None
    assert controller.name is None

    with pytest.raises(RuntimeError):
        controller.ensure_ready(required=("config_path",), interactive=False)


def test_path_prompts(settings, tmp_path, monkeypatch):
    controller = Controller(settings=settings)
    prompts = {
        "Please select/create a folder for the bids-root.": tmp_path / "bids",
        "Please select/create a folder for the derivatives root.": tmp_path / "deriv",
        "Please select/create a folder for saving plots.": tmp_path / "plots",
        "Please enter the path to the FreeSurfer subjects directory": tmp_path
        / "subjects",
    }
    for path in prompts.values():
        path.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        "mne_nodes.pipeline.controller.get_user_input",
        lambda message, *args, **kwargs: prompts[message],
    )
    monkeypatch.setattr("mne_nodes.pipeline.controller.ask_user", lambda *a, **k: True)

    controller.bids_root = None
    controller.deriv_root = None
    controller.plot_root = None
    controller.subjects_dir = None

    assert (
        controller.bids_root
        == prompts["Please select/create a folder for the bids-root."]
    )
    assert (
        controller.deriv_root
        == prompts["Please select/create a folder for the derivatives root."]
    )
    assert (
        controller.plot_root
        == prompts["Please select/create a folder for saving plots."]
    )
    assert (
        controller.subjects_dir
        == prompts["Please enter the path to the FreeSurfer subjects directory"]
    )


def test_load_missing_plugin_metadata(ct, tmp_path, monkeypatch):
    class DummyViewer:
        def load_nodes(self, *_args, **_kwargs):
            return None

    imported_nodes = {"nodes": {"input": {"name": "Input-0"}}, "connections": {}}
    import_payload = {
        "node_config": imported_nodes,
        "plugin_meta": {
            "test_module": {
                "plugin_github": "https://github.com/org/test_module",
                "plugin_type": "github",
            }
        },
        "parameters": {"test_func1": {"a": 12}},
    }
    import_path = tmp_path / "pipeline_import_missing_module.json"
    with open(import_path, "w") as file:
        json.dump(import_payload, file, indent=4, cls=TypedJSONEncoder)

    loaded_plugins = []
    monkeypatch.setattr(
        ct, "load_plugin_github", lambda plugin_url: loaded_plugins.append(plugin_url)
    )
    monkeypatch.setitem(_widgets, "viewer", DummyViewer())
    monkeypatch.setitem(_widgets, "main_window", object())

    ct.config_path = import_path

    assert loaded_plugins == ["https://github.com/org/test_module"]
    assert ct.get("node_config") == imported_nodes


def test_import_plugin_from_config_file(ct, tmp_path):
    plugin_name = "config_file_plugin"
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    script_path = plugin_dir / f"{plugin_name}.py"
    config_path = plugin_dir / f"{plugin_name}_config.json"
    script_path.write_text(
        "def imported_function(value):\n    return value * 2\n", encoding="utf-8"
    )
    config_path.write_text(
        json.dumps(
            {
                "imported_function": {
                    "inputs": {},
                    "outputs": {},
                    "parameters": {},
                    "target": "file",
                }
            }
        ),
        encoding="utf-8",
    )

    ct.load_plugin_path(config_path)

    assert plugin_name in ct.plugins
    assert ct.plugins[plugin_name].imported_function(3) == 6
    assert ct.get_plugin_from_function("imported_function") == plugin_name
    assert ct.get("plugin_meta")[plugin_name] == {
        "config_path": config_path,
        "script_path": script_path,
        "plugin_type": "path",
    }


def test_pipeline_roundtrip(ct, tmp_path, monkeypatch):
    roundtrip_nodes = {
        "nodes": {"input": {"name": "Input-0"}, "filter": {"name": "test_filter"}},
        "connections": {"conn_0": {"source": "Input-0", "target": "filter"}},
    }
    roundtrip_parameters = {
        "test_filter": {"l_freq": 1.0, "h_freq": 40.0},
        "test_epochs": {"tmin": -0.2, "tmax": 0.5},
    }
    ct.set("parameters", roundtrip_parameters)
    ct.set("node_config", roundtrip_nodes)

    export_path = tmp_path / "pipeline_roundtrip.json"
    ct.export_pipeline(export_path)

    ct.set("parameters", {})
    ct.set("node_config", {})
    ct.config_path = export_path
    ct.load(plugins=True)

    assert export_path.exists(), "Roundtrip export should create a JSON file"
    assert ct.get("parameters") == roundtrip_parameters
    assert ct.get("node_config") == roundtrip_nodes


@pytest.mark.timeout(180)
def test_codegen_pipeline(qtbot, tmp_path, monkeypatch, settings):
    from mne_nodes.conftest import _add_complex_nodes, create_test_controller
    from mne_nodes.gui.node.node_viewer import NodeViewer
    from mne_nodes.pipeline.code_generation import CodeGenerator

    monkeypatch.setattr(Controller, "load_recent_plugins", lambda self: self.plugins)
    ct = create_test_controller(
        settings=settings, tmp_path=tmp_path, monkeypatch=monkeypatch
    )
    default_plugin = next(iter(ct.plugins))
    for function_meta in ct.function_meta.values():
        function_meta.setdefault("class_name", None)
        function_meta.setdefault("plugin_name", default_plugin)

    viewer = NodeViewer(ct)
    qtbot.addWidget(viewer)
    _add_complex_nodes(viewer)

    eeg_files = []
    for extension in (".vhdr", ".edf", ".bdf", ".set"):
        eeg_files = sorted(ct.bids_root.rglob(f"*_eeg{extension}"))
        if len(eeg_files) > 0:
            break
    assert len(eeg_files) > 0, "tiny_bids fixture should provide at least one EEG file"

    deriv_root = tmp_path / "derivatives"
    deriv_root.mkdir(parents=True, exist_ok=True)
    ct.deriv_root = deriv_root
    ct.set("selected_inputs", {"eeg": [eeg_files[0].name]})
    ct.flush()

    node_sequence = viewer.get_node_sequence(viewer.input_node)
    # Keep all outputs in-memory to avoid filesystem format assumptions.
    for node in node_sequence:
        node["checked"] = False

    generated_code = CodeGenerator(ct, node_sequence).code
    validation_config_path = Path(__file__).parent / "validation_functions_config.json"
    generated_code = generated_code.replace(
        "# Load controller\n",
        "# Load controller\nController.load_recent_plugins = lambda self: self.plugins\n",
        1,
    )
    generated_code = generated_code.replace(
        "\n\n# Inject plugins into global namespace\n",
        (
            f"\nct.load_plugin_path('{validation_config_path.as_posix()}')\n\n"
            "# Inject plugins into global namespace\n"
        ),
        1,
    )
    script_path = tmp_path / "generated_pipeline.py"
    script_path.write_text(generated_code, encoding="utf-8")

    env = os.environ.copy()
    env["MPLBACKEND"] = "Agg"
    completed = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True,
        text=True,
        env=env,
        timeout=180,
        check=False,
    )
    assert completed.returncode == 0, (
        "Generated script failed.\n"
        f"STDOUT:\n{completed.stdout}\n"
        f"STDERR:\n{completed.stderr}"
    )


# ToDo: add a test about accessing config-variables with .get from Base-Widgets with permanent reference

# ToDo: add a test about accessing and modifying config from multiple processes without data loss or race conditions


def test_load_plugin_path_saves_to_settings_on_missing(
    ct, tmp_path, make_plugin, monkeypatch
):
    """When the stored plugin path is missing, the re-selected path is saved to settings."""
    plugin_name = "relocate_plugin"
    new_plugin_dir = tmp_path / "new_location"
    new_config_path, new_script_path = make_plugin(new_plugin_dir, plugin_name)

    # Simulate missing config path – point to a non-existent file
    missing_path = tmp_path / "old_location" / f"{plugin_name}_config.json"

    monkeypatch.setattr(
        "mne_nodes.pipeline.controller.raise_user_attention", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "mne_nodes.pipeline.controller.get_user_input", lambda *a, **k: new_config_path
    )

    ct.load_plugin_path(missing_path)

    assert plugin_name in ct.plugins
    # New path must be stored in settings.plugin_config
    plugin_config = ct.settings.get("plugin_config") or {}
    assert plugin_name in plugin_config
    assert Path(plugin_config[plugin_name]["config_path"]) == new_config_path
    assert Path(plugin_config[plugin_name]["script_path"]) == new_script_path


def test_load_recent_plugins_uses_settings_override(
    ct, tmp_path, make_plugin, monkeypatch
):
    """load_recent_plugins uses the device-specific path from settings, not the config path."""
    plugin_name = "device_plugin"
    new_plugin_dir = tmp_path / "device_location"
    new_config_path, new_script_path = make_plugin(new_plugin_dir, plugin_name)

    # Pre-populate settings with the device-specific path
    ct.settings.set(
        "plugin_config",
        {plugin_name: {"config_path": new_config_path, "script_path": new_script_path}},
    )
    # Store a stale (non-existent) path in plugin_meta in the config
    stale_path = tmp_path / "stale_location" / f"{plugin_name}_config.json"
    ct.set_dict_value(
        "plugin_meta",
        plugin_name,
        {
            "config_path": stale_path,
            "script_path": stale_path.parent / f"{plugin_name}.py",
            "plugin_type": "path",
        },
    )

    # load_recent_plugins should pick up the settings override, not the stale config path
    loaded_paths = []
    original = ct.load_plugin_path

    def capture_load(config_path):
        loaded_paths.append(Path(config_path))
        return original(config_path)

    monkeypatch.setattr(ct, "load_plugin_path", capture_load)
    ct.load_recent_plugins()

    assert new_config_path in loaded_paths, (
        "load_recent_plugins should use the settings override path"
    )
    assert stale_path not in loaded_paths, (
        "load_recent_plugins should not use the stale config path"
    )


def test_get_dataset_name_caches_to_config(ct, settings, tmp_path, monkeypatch):
    """get_dataset_name stores the name in config and returns it even without bids_root."""
    bids_root = tmp_path / "bids"
    bids_root.mkdir()
    desc = bids_root / "dataset_description.json"
    desc.write_text(json.dumps({"Name": "TestDataset"}), encoding="utf-8")

    monkeypatch.setattr("mne_nodes.pipeline.controller.ask_user", lambda *a, **k: True)
    ct.settings.set("bids_root", bids_root)

    name = ct.get_dataset_name()
    assert name == "TestDataset"
    # Must be persisted in config
    assert ct.get("bids_dataset_name") == "TestDataset"

    # Now remove bids_root from settings – should fall back to cached config value
    ct.settings.remove("bids_root")
    cached_name = ct.get_dataset_name()
    assert cached_name == "TestDataset"
