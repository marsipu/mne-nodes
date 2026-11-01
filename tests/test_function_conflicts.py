"""Conflict choices, persistent aliases and local source renaming."""

import json
from copy import deepcopy
from types import ModuleType
from unittest.mock import Mock

import pytest
from qtpy.QtWidgets import QDialog

from mne_nodes.backend.code_generation import CodeGenerator
from mne_nodes.backend.function_conflicts import (
    rename_plugin_function,
    rename_plugin_functions,
)
from mne_nodes.gui.function_conflicts import FunctionConflictDialog


def _plugin(name, result):
    plugin = ModuleType(name)
    plugin.shared = Mock(return_value=result)
    return plugin


def _meta():
    return {
        "inputs": {},
        "outputs": {},
        "parameters": {},
        "class_name": None,
        "target": "file",
    }


def _load(ct, plugin):
    ct.load_plugin(plugin, plugin.__name__, {"config_path": {"shared": _meta()}})


@pytest.mark.parametrize("mode", ["existing", "incoming", "alias"])
def test_choices_persist_and_survive_reverse_load_order(ct, monkeypatch, mode):
    monkeypatch.setattr("mne_nodes.gui_mode", True)
    resolver = Mock(return_value={"shared": (mode, "other_shared")})
    monkeypatch.setattr(
        "mne_nodes.backend.controller.resolve_function_conflicts", resolver
    )
    first, second = _plugin("first", 1), _plugin("second", 2)
    _load(ct, first)
    _load(ct, second)
    resolver.assert_called_once()
    assert "first" in resolver.call_args.args[0]["shared"][0]
    assert "second" in resolver.call_args.args[0]["shared"][1]
    expected = "second" if mode == "incoming" else "first"
    assert ct.get_plugin_from_function("shared") == expected
    if mode == "alias":
        assert ct.get_plugin_from_function("other_shared") == "second"
        assert ct.get_function_meta("other_shared")["callable_name"] == "shared"
    aliases = deepcopy(ct.get("function_aliases"))
    ct._unload_plugin_session("first")
    ct._unload_plugin_session("second")
    resolver.reset_mock()
    monkeypatch.setattr("mne_nodes.gui_mode", False)
    _load(ct, second)
    _load(ct, first)
    resolver.assert_not_called()
    assert ct.get("function_aliases") == aliases
    assert ct.get_plugin_from_function("shared") == expected


def test_cancel_and_headless_conflicts_do_not_replace(ct, monkeypatch):
    first, second = _plugin("first", 1), _plugin("second", 2)
    _load(ct, first)
    monkeypatch.setattr("mne_nodes.gui_mode", False)
    with pytest.raises(ValueError, match="Unresolved function conflicts"):
        _load(ct, second)
    monkeypatch.setattr("mne_nodes.gui_mode", True)
    monkeypatch.setattr(
        "mne_nodes.backend.controller.resolve_function_conflicts",
        lambda *args, **kwargs: None,
    )
    with pytest.raises(RuntimeError, match="cancelled"):
        _load(ct, second)
    assert ct.get_plugin_from_function("shared") == "first"
    assert "second" not in ct.plugins
    assert ct.get("function_aliases") == {}


def test_alias_generated_pipeline_calls_original(ct, monkeypatch):
    monkeypatch.setattr("mne_nodes.gui_mode", True)
    monkeypatch.setattr(
        "mne_nodes.backend.controller.resolve_function_conflicts",
        lambda *args, **kwargs: {"shared": ("alias", "other_shared")},
    )
    _load(ct, _plugin("first", 1))
    plugin = _plugin("second", 2)
    _load(ct, plugin)
    ct.set("selected_inputs", {"eeg": [ct.get_datatype_items("eeg")[0]]})
    sequence = {
        "file": [
            {
                "name": "other_shared",
                "class": "FunctionNode",
                "inputs": {},
                "outputs": {},
                "checked": False,
                "function_meta": ct.get_function_meta("other_shared"),
            }
        ],
        "group": [],
    }
    generator = CodeGenerator(ct, sequence)
    assert generator._qualified_call("other_shared", set()) == "second.shared"
    monkeypatch.setattr("mne_nodes.backend.controller.Controller", lambda **kwargs: ct)
    exec(compile(generator.code, "<alias-pipeline>", "exec"), {})  # noqa: S102
    plugin.shared.assert_called_once()


def test_dialog_requires_choices_and_unique_identifiers(qtbot):
    dialog = FunctionConflictDialog(
        {"shared": ("first", "second"), "other": ("first", "second")},
        {"shared", "other", "occupied"},
        source_renamable={"shared", "other"},
    )
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)
    dialog.accept()
    assert dialog.result() != QDialog.DialogCode.Accepted
    action, rename = dialog.rows["shared"]
    action.setCurrentIndex(action.findData("alias"))
    assert rename.isEnabled()
    for invalid in ("", "two words", "for", "occupied"):
        rename.setText(invalid)
        dialog.accept()
        assert dialog.result() != QDialog.DialogCode.Accepted
    rename.setText("renamed")
    other_action, other_rename = dialog.rows["other"]
    other_action.setCurrentIndex(other_action.findData("source"))
    other_rename.setText("renamed")
    dialog.accept()
    assert dialog.result() != QDialog.DialogCode.Accepted
    other_rename.setText("other_renamed")
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.choices == {
        "shared": ("alias", "renamed"),
        "other": ("source", "other_renamed"),
    }


@pytest.mark.parametrize("editable", [False, True])
def test_controller_hides_source_rename_for_installed_plugins(
    ct, qtbot, local_source, monkeypatch, editable
):
    """Only editable source files offer disk renaming; node aliases always work."""
    monkeypatch.setattr("mne_nodes.gui_mode", True)
    monkeypatch.setattr(
        "mne_nodes.backend.function_conflicts.plugin_source_is_installed",
        lambda path: not editable,
    )
    _load(ct, _plugin("first", 1))

    def resolve(conflicts, occupied, parent, *, source_renamable):
        dialog = FunctionConflictDialog(
            conflicts, occupied, parent, source_renamable=source_renamable
        )
        qtbot.addWidget(dialog)
        action, rename = dialog.rows["shared"]
        assert (action.findData("source") >= 0) is editable
        action.setCurrentIndex(action.findData("alias"))
        rename.setText("other_shared")
        dialog.accept()
        return dialog.choices

    monkeypatch.setattr(
        "mne_nodes.backend.controller.resolve_function_conflicts", resolve
    )
    script = local_source["script_path"].read_bytes()
    config = local_source["config_path"].read_bytes()
    ct.load_plugin(_plugin("second", 2), "second", local_source)
    assert ct.get_plugin_from_function("other_shared") == "second"
    assert local_source["script_path"].read_bytes() == script
    assert local_source["config_path"].read_bytes() == config


def test_dialog_without_editable_source_has_no_source_rename(qtbot):
    dialog = FunctionConflictDialog({"shared": ("first", "second")}, {"shared"})
    qtbot.addWidget(dialog)
    action, _ = dialog.rows["shared"]
    assert action.findData("source") == -1
    assert action.findData("alias") >= 0


@pytest.fixture
def local_source(tmp_path, monkeypatch):
    script = tmp_path / "local.py"
    script.write_text(
        "def shared(n=2):\n    return shared(n - 1) + 1 if n else 0\n", encoding="utf-8"
    )
    config = script.with_suffix(".json")
    config.write_text(json.dumps({"shared": _meta()}), encoding="utf-8")
    monkeypatch.setattr(
        "mne_nodes.backend.function_conflicts.plugin_source_is_installed",
        lambda path: False,
    )
    return {"script_path": script, "config_path": config}


def test_source_rename_preserves_internal_calls(local_source):
    script_path = local_source["script_path"]
    script_path.write_text(
        script_path.read_text() + "\ninitial = shared(1)\n", encoding="utf-8"
    )
    rename_plugin_function(local_source, "shared", "renamed")
    script = local_source["script_path"].read_text(encoding="utf-8")
    namespace = {}
    exec(compile(script, "<renamed-plugin>", "exec"), namespace)  # noqa: S102
    assert namespace["renamed"](3) == 3
    assert namespace["shared"] is namespace["renamed"]
    assert namespace["initial"] == 1
    assert set(json.loads(local_source["config_path"].read_text())) == {"renamed"}


@pytest.mark.parametrize(
    "code",
    [
        (
            "# Keep this comment\n"
            "def shared():  # and this one\n"
            "    return 'shared stays inside strings'"
        ),
        "async def shared():\n    return 'result'\n",
        "marker = 'caf\u00e9'; from mne.bem import make_watershed_bem as shared\n",
    ],
)
def test_source_edits_preserve_comments_unicode_and_missing_final_newline(
    local_source, code
):
    script = local_source["script_path"]
    script.write_text(code, encoding="utf-8")
    rename_plugin_function(local_source, "shared", "renamed")
    updated = script.read_text(encoding="utf-8")
    namespace = {}
    exec(compile(updated, "<renamed>", "exec"), namespace)  # noqa: S102
    assert namespace["shared"] is namespace["renamed"]
    if code.startswith("#"):
        assert updated.startswith("# Keep this comment\n")
        assert "def renamed():  # and this one" in updated
        assert namespace["renamed"]() == "shared stays inside strings"
    if code.startswith("marker"):
        assert namespace["marker"] == "caf\u00e9"


def test_source_rename_of_imported_watershed_survives_plugin_reload(ct, local_source):
    """Rename the local import, never the third-party MNE implementation."""
    from mne.bem import make_watershed_bem

    script = local_source["script_path"]
    script.write_text(
        'from mne.bem import make_watershed_bem\n\n__all__ = ["make_watershed_bem"]\n',
        encoding="utf-8",
    )
    local_source["config_path"].write_text(
        json.dumps(
            {
                "make_watershed_bem": {
                    **_meta(),
                    "module_name": "mne.bem",
                    "uses_freesurfer": True,
                }
            }
        ),
        encoding="utf-8",
    )
    rename_plugin_function(local_source, "make_watershed_bem", "freesurfer_watershed")
    plugin = ModuleType("watershed")
    exec(script.read_text(), plugin.__dict__)  # noqa: S102
    assert plugin.freesurfer_watershed is make_watershed_bem
    assert plugin.make_watershed_bem is make_watershed_bem
    assert "freesurfer_watershed" in plugin.__all__
    ct.load_plugin(plugin, "watershed", local_source)
    assert ct.get_plugin_from_function("freesurfer_watershed") == "watershed"
    assert ct.plugins["watershed"].freesurfer_watershed is make_watershed_bem


@pytest.mark.parametrize(
    "code",
    [
        "from mne.bem import make_watershed_bem as shared\n",
        "from mne.bem import (\n    make_watershed_bem as shared,\n)\n",
    ],
)
def test_source_rename_preserves_import_aliases_and_multiline_layout(
    local_source, code
):
    from mne.bem import make_watershed_bem

    script = local_source["script_path"]
    script.write_text(code + "\ninitial = shared\n", encoding="utf-8")
    rename_plugin_function(local_source, "shared", "renamed")
    namespace = {}
    exec(script.read_text(), namespace)  # noqa: S102
    assert namespace["initial"] is make_watershed_bem
    assert namespace["renamed"] is make_watershed_bem
    assert namespace["shared"] is make_watershed_bem


def test_source_choice_reloads_without_dialog(ct, monkeypatch, local_source):
    monkeypatch.setattr("mne_nodes.gui_mode", True)
    resolver = Mock(return_value={"shared": ("source", "renamed")})
    monkeypatch.setattr(
        "mne_nodes.backend.controller.resolve_function_conflicts", resolver
    )
    _load(ct, _plugin("first", 1))
    plugin = _plugin("second", 2)
    ct.load_plugin(plugin, "second", local_source)
    assert plugin.renamed is plugin.shared
    assert ct.get_function_meta("renamed")["callable_name"] == "renamed"
    ct._unload_plugin_session("second")
    reloaded = ModuleType("second")
    exec(local_source["script_path"].read_text(), reloaded.__dict__)  # noqa: S102
    resolver.reset_mock()
    ct.load_plugin(reloaded, "second", local_source)
    resolver.assert_not_called()
    assert reloaded.renamed(3) == 3
    assert reloaded.renamed.__name__ == "renamed"
    assert ct.get_plugin_from_function("renamed") == "second"


@pytest.mark.parametrize("retry", ["source", "alias", "cancel"])
def test_rename_failure_notifies_and_allows_retry(ct, monkeypatch, local_source, retry):
    """Failed disk renames never leak changes into the active plugin registry."""
    monkeypatch.setattr("mne_nodes.gui_mode", True)
    _load(ct, _plugin("first", 1))
    resolver = Mock(
        side_effect=[
            {"shared": ("source", "renamed")},
            None if retry == "cancel" else {"shared": (retry, "renamed")},
        ]
    )
    monkeypatch.setattr(
        "mne_nodes.backend.controller.resolve_function_conflicts", resolver
    )
    attention = Mock()
    monkeypatch.setattr(
        "mne_nodes.backend.function_conflicts.raise_user_attention", attention
    )
    from mne_nodes.backend import function_conflicts

    rename = function_conflicts._rename_plugin_functions

    def fail_once(*args):
        if attention.call_count == 0:
            raise OSError("Temporary write failure")
        return rename(*args)

    monkeypatch.setattr(function_conflicts, "_rename_plugin_functions", fail_once)
    plugin = _plugin("second", 2)
    before = local_source["script_path"].read_bytes()
    if retry == "cancel":
        with pytest.raises(RuntimeError, match="cancelled"):
            ct.load_plugin(plugin, "second", local_source)
        assert "second" not in ct.plugins
        assert ct.get("function_aliases") == {}
    else:
        ct.load_plugin(plugin, "second", local_source)
        assert ct.get_plugin_from_function("renamed") == "second"
        assert ct.get_function_meta("renamed")["callable_name"] == (
            "renamed" if retry == "source" else "shared"
        )
    if retry != "source":
        assert local_source["script_path"].read_bytes() == before
        assert not hasattr(plugin, "renamed")
    assert ct.get_plugin_from_function("shared") == "first"
    assert resolver.call_count == 2
    attention.assert_called_once()
    assert "Temporary write failure" in attention.call_args.args[0]


@pytest.mark.parametrize("reason", ["installed", "missing", "occupied"])
def test_source_rename_rejects_unsafe_changes(local_source, monkeypatch, reason):
    script, config = local_source["script_path"], local_source["config_path"]
    if reason == "installed":
        monkeypatch.setattr(
            "mne_nodes.backend.function_conflicts.plugin_source_is_installed",
            lambda path: True,
        )
    elif reason == "missing":
        script.write_text("from somewhere import different\n", encoding="utf-8")
    else:
        script.write_text(script.read_text() + "\nrenamed = 1\n", encoding="utf-8")
    before = (script.read_bytes(), config.read_bytes())
    attention = Mock()
    monkeypatch.setattr(
        "mne_nodes.backend.function_conflicts.raise_user_attention", attention
    )
    assert not rename_plugin_function(local_source, "shared", "renamed")
    attention.assert_called_once()
    assert attention.call_args.args[1] == "error"
    assert (script.read_bytes(), config.read_bytes()) == before


def test_source_write_failure_restores_pair(local_source, monkeypatch):
    from pathlib import Path

    script, config = local_source["script_path"], local_source["config_path"]
    before = (script.read_bytes(), config.read_bytes())
    write = Path.write_text

    def fail_config(path, *args, **kwargs):
        if path == config:
            raise OSError("Simulated write failure")
        return write(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_config)
    attention = Mock()
    monkeypatch.setattr(
        "mne_nodes.backend.function_conflicts.raise_user_attention", attention
    )
    assert not rename_plugin_function(local_source, "shared", "renamed")
    assert "Simulated" in attention.call_args.args[0]
    assert (script.read_bytes(), config.read_bytes()) == before


def test_invalid_second_source_rename_does_not_write_first(local_source, monkeypatch):
    script, config = local_source["script_path"], local_source["config_path"]
    before = (script.read_bytes(), config.read_bytes())
    attention = Mock()
    monkeypatch.setattr(
        "mne_nodes.backend.function_conflicts.raise_user_attention", attention
    )
    assert not rename_plugin_functions(
        local_source, {"shared": "renamed", "missing": "other"}
    )
    assert "top-level" in attention.call_args.args[0]
    assert (script.read_bytes(), config.read_bytes()) == before


def test_saved_alias_does_not_silently_hide_new_function(ct):
    ct.set("function_aliases", {"first": {"shared": "other"}})
    plugin = _plugin("first", 1)
    plugin.other = Mock()
    with pytest.raises(ValueError, match="Duplicate saved"):
        ct.load_plugin(
            plugin, "first", {"config_path": {"shared": _meta(), "other": _meta()}}
        )


def test_switching_plugin_refreshes_connected_nodes(nodeviewer, monkeypatch):
    ct = nodeviewer.ct
    monkeypatch.setattr("mne_nodes.gui_mode", True)
    monkeypatch.setattr(
        "mne_nodes.backend.controller.resolve_function_conflicts",
        lambda *args, **kwargs: {"test_filter": ("incoming", "")},
    )
    node = next(
        node for node in nodeviewer.nodes.values() if node.name == "test_filter"
    )
    position = node.pos()
    eeg = nodeviewer.input_node.output(port_name="eeg")
    assert node.input(port_name="raw") in eeg.connected_ports
    metadata = deepcopy(ct.get_function_meta("test_filter"))
    plugin = ModuleType("replacement")
    plugin.test_filter = Mock()
    ct.load_plugin(plugin, "replacement", {"config_path": {"test_filter": metadata}})
    updated = next(
        node for node in nodeviewer.nodes.values() if node.name == "test_filter"
    )
    assert updated is not node
    assert updated.pos() == position
    assert updated.input(port_name="raw") in eeg.connected_ports


@pytest.mark.parametrize("mode", ["existing", "incoming", "alias"])
def test_choices_survive_new_controller_from_saved_pipeline(
    ct, monkeypatch, tmp_path, mode
):
    from mne_nodes.backend.controller import Controller

    monkeypatch.setattr("mne_nodes.gui_mode", True)
    resolver = Mock(return_value={"shared": (mode, "other_shared")})
    monkeypatch.setattr(
        "mne_nodes.backend.controller.resolve_function_conflicts", resolver
    )
    for name, result in (("conflict_first", 1), ("conflict_second", 2)):
        script = tmp_path / f"{name}.py"
        script.write_text(f"def shared():\n    return {result}\n", encoding="utf-8")
        config = tmp_path / f"{name}_config.json"
        config.write_text(json.dumps({"shared": _meta()}), encoding="utf-8")
        ct.load_plugin_path(config)
    ct.flush()
    expected = deepcopy(ct.get("function_aliases"))
    assert json.loads(ct.config_path.read_text())["function_aliases"] == expected
    monkeypatch.setattr("mne_nodes.gui_mode", False)
    resolver.reset_mock()
    reopened = Controller(config_path=ct.config_path, settings=ct.settings)
    assert reopened.get("function_aliases") == expected
    resolver.assert_not_called()
    assert reopened.get_plugin_from_function("shared") == (
        "conflict_second" if mode == "incoming" else "conflict_first"
    )
    if mode == "alias":
        assert reopened.get_plugin_from_function("other_shared") == "conflict_second"
        assert reopened.plugins["conflict_second"].shared() == 2
