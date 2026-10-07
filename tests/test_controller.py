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

from mne_nodes.backend.controller import Controller
from mne_nodes.backend.io import TypedJSONEncoder
from mne_nodes.backend.pipeline_utils import change_file_section


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


def test_remove_plugin_unregisters_without_deleting_files(
    ct, test_plugin_config, test_script
):
    ct.load_plugin_path(test_plugin_config)
    ct.settings.set("disabled_plugins", ["test_module"])

    ct.remove_plugin("test_module")

    assert test_plugin_config.is_file()
    assert test_script.is_file()
    assert "test_module" not in ct.plugins
    assert "test_module" not in ct.get("plugin_meta")

    assert "test_module" not in ct.settings.get("plugin_config", {})
    assert "test_module" not in ct.settings.get("disabled_plugins", [])


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
        "mne_nodes.backend.controller.ask_user_custom", lambda *a, **k: False
    )
    # Path to existing config-file
    monkeypatch.setattr(
        "mne_nodes.backend.controller.get_user_input", lambda *a, **k: new_config_path
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


@pytest.mark.parametrize("action", ["load", "new", "save_as"])
def test_config_switch_confirms_bids_and_resets_outputs(
    ct, tmp_path, monkeypatch, action
):
    dataset_name = ct.get_dataset_name()
    root = ct.bids_root
    ct.deriv_root = tmp_path
    ct.plot_root = tmp_path
    new_config = tmp_path / "other_pipeline.json"
    new_config.write_text(
        json.dumps(
            {
                "name": "other",
                "bids_dataset_name": dataset_name,
                "selected_inputs": {"subject": ["01"]},
                "custom_groups": {"group": ["01"]},
            }
        ),
        encoding="utf-8",
    )
    confirmations = []
    monkeypatch.setattr(
        "mne_nodes.backend.controller.ask_user",
        lambda message, **kwargs: confirmations.append(message) or True,
    )
    actions = {
        "load": ct.load_config,
        "new": ct.new_config,
        "save_as": ct.save_config_as,
    }
    actions[action](new_config)

    assert len(confirmations) == 1
    assert str(root) in confirmations[0]
    assert ct.bids_root == root
    assert ct.deriv_root is None
    assert ct.plot_root is None
    if action == "load":
        assert ct.get("selected_inputs") == {"subject": ["01"]}
        assert ct.get("custom_groups") == {"group": ["01"]}
    ct.load()
    ct.config_path = new_config
    assert len(confirmations) == 1


def test_config_switch_reselects_bids_root(ct, tmp_path, monkeypatch):
    new_root = tmp_path / "other_bids"
    new_root.mkdir()
    (new_root / "dataset_description.json").write_text(
        json.dumps({"Name": "Other dataset"}), encoding="utf-8"
    )
    new_config = tmp_path / "other_pipeline.json"
    new_config.write_text(
        json.dumps(
            {
                "name": "other",
                "bids_dataset_name": ct.get_dataset_name(),
                "selected_inputs": {"subject": ["01"]},
                "custom_groups": {"group": ["01"]},
            }
        ),
        encoding="utf-8",
    )
    confirmations = []
    monkeypatch.setattr(
        "mne_nodes.backend.controller.ask_user",
        lambda message, **kwargs: confirmations.append(message) or False,
    )
    monkeypatch.setattr(
        "mne_nodes.backend.controller.get_user_input", lambda *args, **kwargs: new_root
    )

    ct.load_config(new_config)

    assert len(confirmations) == 1
    assert ct.bids_root == new_root
    assert ct.get("bids_dataset_name") == "Other dataset"
    assert ct.get("selected_inputs") == {}
    assert ct.get("custom_groups") == {}
    ct.flush()
    ct.load()
    assert ct.get("bids_dataset_name") == "Other dataset"


def test_config_output_roots_share_parent(ct, tmp_path, monkeypatch):
    ct.set("name", "first")
    prompts = []
    monkeypatch.setattr(
        "mne_nodes.backend.controller.get_user_input",
        lambda message, *args, **kwargs: prompts.append(message) or tmp_path,
    )
    ct.ensure_ready(required=("deriv_root", "plot_root"))
    assert len(prompts) == 1
    assert ct.deriv_root == tmp_path / "first_derivatives"
    assert ct.plot_root == tmp_path / "first_plots"
    assert ct.plot_path == ct.plot_root
    assert ct.deriv_root.is_dir()
    assert ct.plot_root.is_dir()

    ct.flush()
    reloaded = Controller(config_path=ct.config_path, settings=ct.settings)
    assert reloaded.plot_path == ct.plot_root
    assert len(prompts) == 1

    new_config = tmp_path / "second_pipeline.json"
    new_config.write_text(json.dumps({"name": "second"}), encoding="utf-8")
    ct.load_config(new_config)
    with pytest.raises(RuntimeError):
        ct.ensure_deriv_root(interactive=False)
    ct.ensure_ready(required=("deriv_root", "plot_root"))
    assert len(prompts) == 2
    assert ct.deriv_root == tmp_path / "second_derivatives"
    assert ct.plot_path == tmp_path / "second_plots"


def test_startup_config_switch_defers_confirmation(ct, tmp_path, monkeypatch):
    ct.deriv_root = tmp_path
    ct.plot_root = tmp_path
    config_path = tmp_path / "startup_pipeline.json"
    config_path.write_text(json.dumps({"name": "startup"}), encoding="utf-8")
    confirmations = []
    monkeypatch.setattr(
        "mne_nodes.backend.controller.ask_user",
        lambda message, **kwargs: confirmations.append(message) or True,
    )
    controller = Controller(config_path=config_path, settings=ct.settings)

    assert confirmations == []
    assert controller.deriv_root is None
    assert controller.plot_root is None
    with pytest.raises(RuntimeError, match="must be confirmed"):
        controller.ensure_bids_root(interactive=False)
    assert controller.ensure_bids_root() == ct.bids_root
    assert len(confirmations) == 1
    controller.ensure_bids_root()
    assert len(confirmations) == 1


def test_config_switch_keeps_root_with_dataset_mismatch(ct, tmp_path, monkeypatch):
    config_path = tmp_path / "mismatch_pipeline.json"
    config_path.write_text(
        json.dumps(
            {
                "name": "mismatch",
                "bids_dataset_name": "different dataset",
                "selected_inputs": {"subject": ["01"]},
                "custom_groups": {"group": ["01"]},
            }
        ),
        encoding="utf-8",
    )
    root = ct.bids_root
    warnings = []
    monkeypatch.setattr(
        "mne_nodes.backend.controller.raise_user_attention",
        lambda message: warnings.append(message),
    )
    ct.load_config(config_path)

    assert ct.bids_root == root
    assert len(warnings) == 1
    assert "different dataset" in warnings[0]
    assert ct.get("selected_inputs") == {}
    assert ct.get("custom_groups") == {}
    assert ct.get("bids_dataset_name") == ct._read_bids_dataset_name(root)


def test_explicit_output_roots_keep_legacy_layout(ct, tmp_path):
    ct.deriv_root = tmp_path
    ct.plot_root = tmp_path

    assert ct.ensure_deriv_root(interactive=False) == tmp_path
    assert ct.ensure_plot_root(interactive=False) == tmp_path
    assert ct.plot_path == tmp_path / ct.name


@pytest.mark.parametrize(
    ("action", "method"),
    [
        ("new_pipeline", "new_config"),
        ("load_pipeline", "load_config"),
        ("save_pipeline_as", "save_config_as"),
    ],
)
def test_gui_config_actions_initialize_output_roots(
    ct, qtbot, tmp_path, monkeypatch, action, method
):
    from mne_nodes.backend.controller import default_config
    from mne_nodes.gui.main_window import MainWindow

    monkeypatch.setattr(ct, "get_datatype_items", dict)
    window = MainWindow(ct)
    qtbot.addWidget(window)
    ct.deriv_root = tmp_path
    ct.plot_root = tmp_path
    config_path = tmp_path / "gui_pipeline.json"
    config_path.write_text(
        json.dumps({**default_config, "name": "gui"}), encoding="utf-8"
    )
    original_method = getattr(ct, method)
    monkeypatch.setattr(ct, method, lambda: original_method(config_path))
    prompts = []
    monkeypatch.setattr(
        "mne_nodes.backend.controller.get_user_input",
        lambda message, *args, **kwargs: prompts.append(message) or tmp_path,
    )

    getattr(window, action)()

    assert ct.config_path == config_path
    assert len(prompts) == 1
    assert ct.deriv_root == tmp_path / f"{ct.name}_derivatives"
    assert ct.plot_path == tmp_path / f"{ct.name}_plots"
    ct.ensure_ready(interactive=False)


def test_path_prompts(settings, tmp_path, monkeypatch):
    controller = Controller(settings=settings)
    controller.set("name", "test")
    prompts = {
        "Please select/create a folder for the bids-root.": tmp_path / "bids",
        "Select the parent folder for 'test_derivatives' and 'test_plots'.": tmp_path
        / "outputs",
        "Please enter the path to the FreeSurfer subjects directory": tmp_path
        / "subjects",
    }
    for path in prompts.values():
        path.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        "mne_nodes.backend.controller.get_user_input",
        lambda message, *args, **kwargs: prompts[message],
    )
    monkeypatch.setattr("mne_nodes.backend.controller.ask_user", lambda *a, **k: True)

    controller.bids_root = None
    controller.deriv_root = None
    controller.plot_root = None
    controller.subjects_dir = None

    assert (
        controller.bids_root
        == prompts["Please select/create a folder for the bids-root."]
    )
    assert controller.deriv_root == tmp_path / "outputs" / "test_derivatives"
    assert controller.plot_root == tmp_path / "outputs" / "test_plots"
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
    viewer = DummyViewer()
    monkeypatch.setattr(type(ct), "viewer", property(lambda self: viewer))

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


@pytest.mark.parametrize("save_as_method", ["save_config_as", "export_pipeline"])
def test_config_file_actions_roundtrip(ct, tmp_path, save_as_method):
    """New, save, save-as/export and load preserve the complete pipeline state."""
    new_config_path = tmp_path / "new_config.json"
    export_path = tmp_path / "pipeline_roundtrip.json"
    ct.new_config(new_config_path)
    ct.set("name", "draft")
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

    ct.save_config()
    assert json.loads(new_config_path.read_text(encoding="utf-8"))["name"] == "draft"
    getattr(ct, save_as_method)(export_path)
    assert ct.config_path == export_path
    assert json.loads(export_path.read_text(encoding="utf-8"))["name"] == "draft"

    ct.set("parameters", {})
    ct.set("node_config", {})
    ct.load_config(export_path)

    assert ct.get("name") == "draft"
    assert ct.get("parameters") == roundtrip_parameters
    assert ct.get("node_config") == roundtrip_nodes


def test_pipeline_file_name_pattern(tmp_path, monkeypatch, settings):
    controller = Controller(settings=settings)

    inputs = iter([tmp_path, "demo_pipeline"])
    monkeypatch.setattr(
        "mne_nodes.backend.controller.get_user_input",
        lambda *args, **kwargs: next(inputs),
    )
    monkeypatch.setattr(
        "mne_nodes.backend.controller.ask_user", lambda *args, **kwargs: True
    )

    saved_path = controller.new_config()
    assert saved_path == tmp_path / "demo_pipeline_pipeline.json"
    assert saved_path.exists()


@pytest.mark.timeout(180)
def test_codegen_pipeline(qtbot, tmp_path, monkeypatch, settings):
    from mne_nodes.backend.code_generation import CodeGenerator
    from mne_nodes.gui.node.node_viewer import NodeViewer
    from tests.conftest import _add_complex_nodes, create_test_controller

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
    for sequence in node_sequence.values():
        for node in sequence:
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
        "mne_nodes.backend.controller.raise_user_attention", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "mne_nodes.backend.controller.get_user_input", lambda *a, **k: new_config_path
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


def test_bids_root_syncs_and_caches_dataset_name(ct, tmp_path):
    """Root changes and name lookups refresh the cache used without a root."""
    root_a = tmp_path / "bids_a"
    root_b = tmp_path / "bids_b"
    root_a.mkdir()
    root_b.mkdir()
    (root_a / "dataset_description.json").write_text(
        json.dumps({"Name": "Dataset A"}), encoding="utf-8"
    )
    (root_b / "dataset_description.json").write_text(
        json.dumps({"Name": "Dataset B"}), encoding="utf-8"
    )

    ct.bids_root = root_a
    assert ct.get("bids_dataset_name") == "Dataset A"

    ct.bids_root = root_b
    assert ct.get("bids_dataset_name") == "Dataset B"
    assert ct.get_dataset_name() == "Dataset B"

    ct.set("bids_dataset_name", "Manual Name")
    assert ct.get("bids_dataset_name") == "Manual Name"
    ct.bids_root = root_a
    assert ct.get("bids_dataset_name") == "Dataset A"
    ct.set("bids_dataset_name", None)
    assert ct.get_dataset_name() == "Dataset A"
    assert ct.get("bids_dataset_name") == "Dataset A"
    ct.settings.remove("bids_root")
    assert ct.get_dataset_name() == "Dataset A"


def test_codegen_multi_type_read_write(ct):
    from mne_nodes.backend.code_generation import CodeGenerator

    plugin_name = next(iter(ct.plugins), "mne_functions")

    # Register metadata for grand_average with dict-based read and write
    ct.function_meta["grand_average"] = {
        "inputs": {
            "all_inst": {
                "accepted_ports": ["all_inst", "evoked", "evokeds", "tfr"],
                "optional": False,
                "read": {
                    "evoked": "read_evokeds",
                    "evokeds": "read_evokeds",
                    "tfr": "read_tfrs",
                },
                "suffix": {"evoked": "ave", "evokeds": "ave", "tfr": "tfr"},
            }
        },
        "parameters": {},
        "outputs": {
            "grand_average": {
                "accepted_ports": ["grand_average", "evoked", "evokeds", "tfr"],
                "write": {
                    "evoked": "write_evokeds",
                    "evokeds": "write_evokeds",
                    "tfr": "write_tfrs",
                },
                "suffix": {"evoked": "ave", "evokeds": "ave", "tfr": "tfr"},
            }
        },
        "target": "group",
        "category": "sensor_space",
        "sub_category": None,
        "class_name": None,
        "module_name": "mne",
        "plugin": plugin_name,
    }
    ct.function_meta["read_evokeds"] = {
        "parameters": {"fname": None},
        "class_name": None,
        "module_name": "mne",
        "plugin": plugin_name,
    }
    ct.function_meta["write_evokeds"] = {
        "parameters": {"fname": None},
        "class_name": None,
        "module_name": "mne",
        "plugin": plugin_name,
    }

    ct.set("selected_inputs", {"subject": ["sub-01", "sub-02"]})

    node_sequence = {
        "file": [],
        "group": [
            {
                "name": "grand_average",
                "class": "FunctionNode",
                "inputs": {"all_inst": ["test_evokeds"]},
                "input_ports": {"all_inst": ["evoked"]},
                "outputs": {"grand_average": ["evoked"]},
                "output_ports": {"grand_average": ["evoked"]},
                "checked": True,
                "function_meta": ct.function_meta["grand_average"],
            }
        ],
    }

    gen = CodeGenerator(ct, node_sequence)
    code = gen.code
    assert "read_evokeds" in code
    assert "suffix='ave'" in code
    assert "write_evokeds" in code
    assert "grand_average(" in code


def test_codegen_multi_type_invalid_connection(ct, caplog):
    import logging

    from mne_nodes.backend.code_generation import CodeGenerator

    plugin_name = next(iter(ct.plugins), "mne_functions")

    ct.function_meta["grand_average"] = {
        "inputs": {
            "all_inst": {
                "accepted_ports": ["all_inst", "evoked"],
                "optional": False,
                "read": {"evoked": "read_evokeds"},
            }
        },
        "parameters": {},
        "outputs": {},
        "target": "file",
        "class_name": None,
        "module_name": "mne",
        "plugin": plugin_name,
    }

    ct.set("selected_inputs", {"eeg": ["sample.vhdr"]})

    node_sequence = {
        "file": [
            {
                "name": "grand_average",
                "class": "FunctionNode",
                "inputs": {"all_inst": ["unknown_node"]},
                "input_ports": {"all_inst": ["unknown_port"]},
                "outputs": {},
                "output_ports": {},
                "checked": False,
                "function_meta": ct.function_meta["grand_average"],
            }
        ],
        "group": [],
    }

    with caplog.at_level(logging.WARNING, logger="mne_nodes"):
        CodeGenerator(ct, node_sequence)
        assert any(
            "Connection is not valid" in record.message or "not valid" in record.message
            for record in caplog.records
        )
