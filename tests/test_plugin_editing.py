"""Safe editing, optional installation and pre-save repository options."""

import json
import shutil
import subprocess
import sys
from dataclasses import replace

import pytest
from qtpy.QtCore import Qt
from qtpy.QtWidgets import QDialog, QPushButton

from mne_nodes.backend.package_utils import install_local_plugin
from mne_nodes.backend.plugin_package import (
    PluginPackageMetadata,
    PluginSource,
    copy_plugin_source,
    create_plugin_package,
    get_plugin_source,
    initialize_plugin_repository,
    plugin_source_is_installed,
)
from mne_nodes.gui.function_widgets import FunctionImporter
from mne_nodes.gui.parameter.plugin_manager import PluginManagerDlg
from mne_nodes.gui.plugin_package import LocalPluginInstallDialog, PluginPackageDialog

CODE = "def transform(value, scale=2):\n    result = value * scale\n    return result\n"
CONFIG = {
    "transform": {
        "inputs": {"value": {"accepted_ports": ["value"], "optional": False}},
        "outputs": {"result": {"accepted_ports": ["result"], "optional": False}},
        "parameters": {"scale": {"default": 2, "gui": "IntGui"}},
        "target": "file",
    }
}


@pytest.fixture
def info():
    return PluginPackageMetadata(
        distribution_name="mne-nodes_edit-fixture",
        description="Plugin editor fixture",
        author="Test contributors",
        license_expression="MIT",
    )


@pytest.fixture
def source(tmp_path, info):
    root = tmp_path / "plugin_project"
    config = create_plugin_package(root, "edit_fixture", CODE, CONFIG, info)
    return PluginSource(config.with_name("edit_fixture.py"), config, root, False)


@pytest.fixture
def errors(monkeypatch):
    captured = []
    for module in ("function_widgets", "parameter.plugin_manager", "main_window"):
        monkeypatch.setattr(
            f"mne_nodes.gui.{module}.ErrorDialog.open",
            lambda self: captured.append(self.windowTitle()),
        )
    return captured


def _editors(manager):
    return manager.findChildren(FunctionImporter)


def test_git_options_are_visible_before_save(qtbot):
    dialog = PluginPackageDialog("git_fixture")
    qtbot.addWidget(dialog)
    available = shutil.which("git") is not None
    assert dialog.initialize_git.isEnabled() == available
    assert dialog.initialize_git.isChecked() == available
    assert dialog.initial_branch.text() == "main"
    assert not dialog.install_package.isChecked()
    assert dialog.editable_install.isChecked()
    dialog.install_package.setChecked(True)
    assert dialog.editable_install.isEnabled()
    dialog.initialize_git.setChecked(False)
    assert not dialog.initial_branch.isEnabled()


def test_git_unavailable_is_explained(qtbot, monkeypatch):
    monkeypatch.setattr("mne_nodes.gui.plugin_package.which", lambda name: None)
    dialog = PluginPackageDialog("git_fixture")
    qtbot.addWidget(dialog)
    assert not dialog.initialize_git.isChecked()
    assert not dialog.initialize_git.isEnabled()
    assert not dialog.initial_branch.isEnabled()


@pytest.mark.skipif(shutil.which("git") is None, reason="Git is unavailable")
def test_git_initialization_main_without_commit_or_remote(tmp_path):
    root = tmp_path / "new_project"
    initialize_plugin_repository(root)

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
        )

    assert git("symbolic-ref", "--short", "HEAD").stdout.strip() == "main"
    assert git("remote").stdout == ""
    assert git("rev-parse", "--verify", "HEAD").returncode != 0
    # Calling it again must not rename an existing branch.
    initialize_plugin_repository(root, "different")
    assert git("symbolic-ref", "--short", "HEAD").stdout.strip() == "main"


@pytest.mark.skipif(shutil.which("git") is None, reason="Git is unavailable")
@pytest.mark.parametrize("branch", ["", "--bad", "bad..branch", "two words"])
def test_invalid_branch_rejected_before_files(tmp_path, info, branch):
    with pytest.raises(ValueError, match="branch"):
        create_plugin_package(
            tmp_path / "project",
            "git_fixture",
            CODE,
            CONFIG,
            replace(info, initialize_git=True, initial_branch=branch),
        )
    assert not (tmp_path / "project").exists()


def test_git_failure_keeps_saved_package_and_allows_retry(
    qtbot, tmp_path, info, monkeypatch, errors
):
    calls = []

    def initialize(root, branch):
        calls.append((root, branch))
        if len(calls) == 1:
            raise RuntimeError("Simulated git failure")

    monkeypatch.setattr(
        "mne_nodes.gui.function_widgets.initialize_plugin_repository", initialize
    )
    importer = FunctionImporter(
        code=CODE,
        plugin_name="git_fixture",
        destination_dir=tmp_path / "project",
        package_metadata=replace(info, initialize_git=True),
    )
    qtbot.addWidget(importer)
    assert not importer.save()
    assert importer.file_path.is_file()
    assert errors == ["Could not save the plugin."]
    assert importer.save()
    assert len(calls) == 2
    importer.func_config.clear()
    importer.close()


@pytest.mark.parametrize("editable", [True, False])
def test_local_install_uses_selected_mode(source, monkeypatch, editable):
    calls = []
    monkeypatch.setattr(
        "mne_nodes.backend.package_utils.install_pip_packages",
        lambda arguments, **kwargs: calls.append(arguments),
    )
    install_local_plugin(source.project_root, editable=editable)
    expected = [str(source.project_root.resolve())]
    if editable:
        expected.insert(0, "--editable")
    assert calls == [expected]


def test_path_install_dialog_defaults_to_editable(qtbot, source):
    dialog = LocalPluginInstallDialog(source.project_root)
    qtbot.addWidget(dialog)
    assert dialog.editable_install.isChecked()
    assert not dialog.install_package.isChecked()
    dialog.install_package.setChecked(True)
    assert dialog.editable_install.isEnabled()


def test_real_editable_install_links_source_without_changing_environment(
    source, tmp_path, info
):
    prefix = tmp_path / "isolated_prefix"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--no-build-isolation",
            "--prefix",
            str(prefix),
            "--editable",
            str(source.project_root),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    (dist_info,) = prefix.rglob("*.dist-info")
    direct_url = json.loads((dist_info / "direct_url.json").read_text())
    assert direct_url["dir_info"]["editable"]
    code = (
        "import site, sys\n"
        "from pathlib import Path\n"
        "site.addsitedir(sys.argv[1])\n"
        "from mne_nodes.backend.package_utils import find_plugin_entry_point\n"
        "from mne_nodes.backend.plugin_package import plugin_source_is_installed\n"
        "plugin = find_plugin_entry_point(sys.argv[2], 'edit_fixture').load()\n"
        "assert plugin.SCRIPT_PATH.resolve() == Path(sys.argv[3]).resolve()\n"
        "assert not plugin_source_is_installed(plugin.SCRIPT_PATH)\n"
    )
    smoke = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(dist_info.parent),
            info.distribution_name,
            str(source.script_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert smoke.returncode == 0, smoke.stdout + smoke.stderr


def test_save_installs_only_when_requested(qtbot, tmp_path, info, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "mne_nodes.gui.function_widgets.install_local_plugin",
        lambda root, **kwargs: calls.append((root, kwargs["editable"])),
    )
    importer = FunctionImporter(
        code=CODE,
        plugin_name="install_fixture",
        destination_dir=tmp_path / "project",
        package_metadata=replace(info, install_package=True, editable_install=False),
    )
    qtbot.addWidget(importer)
    assert importer.save()
    assert calls == [(tmp_path / "project", False)]
    assert importer.save()
    assert len(calls) == 1
    importer.func_config.clear()
    importer.close()


def test_edit_local_plugin_reloads_and_preserves_metadata(main_window, source, qtbot):
    ct = main_window.controller
    ct.load_plugin_path(source.config_path)
    original_meta = ct.get("plugin_meta")["edit_fixture"].copy()
    manager = PluginManagerDlg(main_window, ct)
    group = next(
        group
        for group in manager.findChildren(QPushButton)
        if group.text() == "Edit..."
        and group.parent().property("plugin_name") == "edit_fixture"
    )
    qtbot.mouseClick(group, Qt.MouseButton.LeftButton)
    (editor,) = _editors(manager)
    editor.source_editor.setPlainText(CODE.replace("scale=2", "scale=8"))
    assert editor.save()
    assert ct.plugins["edit_fixture"].transform(2) == 16
    assert ct.get("plugin_meta")["edit_fixture"] == original_meta
    assert (source.project_root / "pyproject.toml").is_file()
    editor.close()
    manager.close()


def test_plugin_reload_refreshes_nodes_in_place(main_window, source):
    ct = main_window.controller
    viewer = ct.viewer
    funcs = ("consume", "keep", "drop")
    source.script_path.write_text(
        CODE + "".join(f"\n\ndef {fn}(result):\n    return result\n" for fn in funcs),
        encoding="utf-8",
    )
    sink = {
        "inputs": {"result": {"accepted_ports": ["result"]}},
        "outputs": {},
        "parameters": {},
        "target": "file",
    }
    config = {**CONFIG, **{fn: json.loads(json.dumps(sink)) for fn in funcs}}
    config["transform"] = json.loads(json.dumps(CONFIG["transform"]))
    config["transform"]["outputs"]["result"]["write"] = True
    source.config_path.write_text(json.dumps(config), encoding="utf-8")
    ct.load_plugin_path(source.config_path)
    nodes = {fn: viewer.add_function_node(fn) for fn in ("transform", *funcs)}
    nodes["transform"].setChecked(True)
    out = nodes["transform"].port(port_type="out", port_name="result")
    for fn in funcs:
        out.connect_to(nodes[fn].port(port_type="in", port_name="result"))
    pos = nodes["transform"].pos()

    # Changed parameters, renamed input and a removed function.
    config["transform"]["parameters"]["offset"] = {"default": 1, "gui": "IntGui"}
    config["consume"]["inputs"] = {"data": {"accepted_ports": ["data"]}}
    del config["drop"]
    source.config_path.write_text(json.dumps(config), encoding="utf-8")
    ct.reload_plugins("edit_fixture")

    assert {"transform", "consume", "keep"} <= set(viewer.function_nodes)
    assert "drop" not in viewer.function_nodes
    transform = viewer.function_nodes["transform"]
    assert transform is not nodes["transform"]
    assert "offset" in transform.parameter_guis
    assert transform.pos() == pos
    assert transform.isChecked()
    assert viewer.function_nodes["keep"] is nodes["keep"]
    out = transform.port(port_type="out", port_name="result")
    assert [p.node.name for p in out.connected_ports] == ["keep"]
    assert viewer.function_nodes["consume"].port(port_name="data").connected_ports == []


def test_edit_disabled_plugin_does_not_enable_it(main_window, source):
    ct = main_window.controller
    ct.load_plugin_path(source.config_path)
    ct.disable_plugin("edit_fixture")
    manager = PluginManagerDlg(main_window, ct)
    manager._edit_plugin("edit_fixture")
    (editor,) = _editors(manager)
    editor.source_editor.setPlainText(CODE.replace("scale=2", "scale=9"))
    assert editor.save()
    assert "edit_fixture" not in ct.plugins
    assert "edit_fixture" in ct.settings.get("disabled_plugins")
    assert "scale=9" in source.script_path.read_text(encoding="utf-8")
    editor.close()
    manager.close()


def test_editor_handles_import_only_scripts_and_configuration(qtbot, source):
    source.script_path.write_text("from math import sqrt\n", encoding="utf-8")
    source.config_path.write_text(json.dumps({"sqrt": CONFIG["transform"]}))
    editor = FunctionImporter(source=source)
    qtbot.addWidget(editor)
    editor.function_cmbx.setCurrentText("sqrt")
    editor.func_config["sqrt"]["target"] = "group"
    editor.package_editors[source.project_root / "README.md"].setPlainText(
        "Updated README\n"
    )
    assert editor.save()
    assert "sqrt" in json.loads(source.config_path.read_text())
    assert json.loads(source.config_path.read_text())["sqrt"]["target"] == "group"
    assert (source.project_root / "README.md").read_text() == "Updated README\n"
    editor.close()


def test_importer_preserves_configuration_until_reanalysis(qtbot, source):
    original_config = source.config_path.read_bytes()
    editor = FunctionImporter(source=source)
    qtbot.addWidget(editor)
    assert editor.function_cmbx.currentText() == "transform"
    assert editor.save()
    assert source.config_path.read_bytes() == original_config
    editor.source_editor.setPlainText(CODE.replace("scale=2", "scale=7"))
    editor.reanalyze()
    assert editor.func_config["transform"]["parameters"]["scale"]["default"] == 7
    assert editor.save()
    assert json.loads(source.config_path.read_text()) == editor.func_config
    editor.close()


def test_importer_reanalysis_keeps_imported_function_configuration(qtbot, source):
    source.script_path.write_text("from math import sqrt\n" + CODE, encoding="utf-8")
    source.config_path.write_text(
        json.dumps({**CONFIG, "sqrt": CONFIG["transform"]}), encoding="utf-8"
    )
    editor = FunctionImporter(source=source)
    qtbot.addWidget(editor)
    editor.reanalyze()
    assert set(editor.func_config) == {"transform", "sqrt"}
    editor.function_cmbx.setCurrentText("sqrt")
    assert editor.current_func == "sqrt"
    assert editor.save()
    editor.close()


def test_importer_edits_package_configuration_without_recreating(qtbot, source):
    project = source.project_root / "pyproject.toml"
    original = project.read_text(encoding="utf-8")
    editor = FunctionImporter(source=source)
    qtbot.addWidget(editor)
    editor.package_editors[project].setPlainText(
        original.replace('version = "0.1.0"', 'version = "0.2.0"')
    )
    assert editor.save()
    assert 'version = "0.2.0"' in project.read_text(encoding="utf-8")
    assert source.script_path.read_text(encoding="utf-8") == CODE
    editor.close()


@pytest.mark.parametrize("invalid", ["source", "json", "toml"])
def test_editor_validates_everything_before_writing(qtbot, source, errors, invalid):
    originals = {
        path: path.read_bytes()
        for path in (
            source.script_path,
            source.config_path,
            source.project_root / "pyproject.toml",
        )
    }
    editor = FunctionImporter(source=source)
    qtbot.addWidget(editor)
    editor.source_editor.setPlainText(CODE.replace("scale=2", "scale=5"))
    if invalid == "source":
        editor.source_editor.setPlainText("def broken(:")
    elif invalid == "json":
        editor.func_config["transform"] = []
    else:
        editor.package_editors[source.project_root / "pyproject.toml"].setPlainText(
            "[broken"
        )
    assert not editor.save()
    assert errors == ["Could not save plugin changes."]
    assert all(path.read_bytes() == text for path, text in originals.items())
    editor._original.update(editor._existing_plugin_contents())
    editor.close()


def test_editor_refuses_external_changes(qtbot, source, errors):
    editor = FunctionImporter(source=source)
    qtbot.addWidget(editor)
    editor.source_editor.setPlainText(CODE.replace("scale=2", "scale=5"))
    source.script_path.write_text("# external edit\n" + CODE, encoding="utf-8")
    assert not editor.save()
    assert source.script_path.read_text().startswith("# external edit")
    assert errors == ["Could not save plugin changes."]
    editor._original[source.script_path] = editor.source_editor.toPlainText()
    editor.close()


def test_editor_reload_failure_can_be_retried(qtbot, source, errors):
    calls = []

    def reload(config_path):
        calls.append(True)
        if len(calls) == 1:
            raise ImportError("Broken import")

    editor = FunctionImporter(source=source, on_saved=reload)
    qtbot.addWidget(editor)
    editor.source_editor.setPlainText(CODE.replace("scale=2", "scale=4"))
    assert not editor.save()
    assert errors == ["Plugin files were saved, but could not be reloaded."]
    assert editor.save()
    assert len(calls) == 2
    editor.close()


def test_editor_close_cancellation_preserves_unsaved_changes(
    qtbot, source, monkeypatch
):
    editor = FunctionImporter(source=source)
    qtbot.addWidget(editor)
    editor.show()
    editor.source_editor.setPlainText(CODE.replace("scale=2", "scale=3"))
    monkeypatch.setattr(
        "mne_nodes.gui.function_widgets.ask_user_custom", lambda *a, **k: None
    )
    assert not editor.close()
    assert editor.isVisible()
    assert source.script_path.read_text() == CODE
    monkeypatch.setattr(
        "mne_nodes.gui.function_widgets.ask_user_custom", lambda *a, **k: False
    )
    assert editor.close()


def test_environment_source_is_never_editable(qtbot, source, monkeypatch):
    monkeypatch.setattr(
        "mne_nodes.backend.plugin_package.sysconfig.get_path",
        lambda key: str(source.project_root),
    )
    assert plugin_source_is_installed(source.script_path)
    resolved = get_plugin_source(
        {"config_path": source.config_path, "script_path": source.script_path}
    )
    assert resolved.installed
    with pytest.raises(ValueError, match="Copy"):
        FunctionImporter(source=resolved)
    with pytest.raises(ValueError, match="environment file"):
        FunctionImporter(source=source)


def test_ordinary_distribution_file_is_protected_but_editable_source_is_not(
    tmp_path, source, monkeypatch
):
    distribution_root = source.project_root
    dist = distribution_root / "edit_fixture-0.1.0.dist-info"
    dist.mkdir()
    (dist / "METADATA").write_text(
        "Metadata-Version: 2.4\nName: edit-fixture\nVersion: 0.1.0\n"
    )
    relative = source.script_path.relative_to(distribution_root).as_posix()
    (dist / "RECORD").write_text(f"{relative},,\n")
    monkeypatch.syspath_prepend(str(distribution_root))
    assert plugin_source_is_installed(source.script_path)
    (dist / "direct_url.json").write_text(
        json.dumps({"url": distribution_root.as_uri(), "dir_info": {"editable": True}})
    )
    assert not plugin_source_is_installed(source.script_path)


@pytest.mark.parametrize("disabled", [True, False])
def test_installed_plugin_edit_makes_local_copy_without_touching_original(
    main_window, source, tmp_path, info, monkeypatch, disabled
):
    helper = source.script_path.parent / "helper.py"
    helper.write_text("def multiply(value):\n    return value * 11\n")
    source.script_path.write_text(
        "from .helper import multiply\n\ndef transform(value):\n"
        "    return multiply(value)\n"
    )
    original_bytes = {
        path: path.read_bytes()
        for path in source.project_root.rglob("*")
        if path.is_file()
    }
    ct = main_window.controller
    ct.load_plugin_path(source.config_path)
    if disabled:
        ct.disable_plugin("edit_fixture")
    # Simulate the installed source while leaving the new copy local.
    original_source = get_plugin_source(ct.get("plugin_meta")["edit_fixture"])
    monkeypatch.setattr(
        "mne_nodes.gui.parameter.plugin_manager.get_plugin_source",
        lambda *args: replace(original_source, installed=True),
    )
    monkeypatch.setattr(
        "mne_nodes.gui.parameter.plugin_manager.ask_user", lambda *args, **kwargs: True
    )
    monkeypatch.setattr(
        "mne_nodes.gui.parameter.plugin_manager.request_package_metadata",
        lambda *args: info,
    )
    destination = tmp_path / "local_copy"
    monkeypatch.setattr(
        "mne_nodes.gui.parameter.plugin_manager.get_user_input",
        lambda *args, **kwargs: destination,
    )
    manager = PluginManagerDlg(main_window, ct)
    manager._edit_plugin("edit_fixture")
    (editor,) = _editors(manager)
    assert editor.source.script_path.is_relative_to(destination)
    assert (editor.source.script_path.parent / "helper.py").is_file()
    assert editor.save()
    assert ct.get("plugin_meta")["edit_fixture"]["config_path"].is_relative_to(
        destination
    )
    if disabled:
        assert "edit_fixture" not in ct.plugins
        assert "edit_fixture" in ct.settings.get("disabled_plugins")
    else:
        assert ct.plugins["edit_fixture"].transform(2) == 22
    assert all(path.read_bytes() == content for path, content in original_bytes.items())
    editor.close()
    manager.close()


def test_copy_refuses_destination_inside_source(source, info):
    with pytest.raises(ValueError, match="outside"):
        copy_plugin_source(source, source.script_path.parent / "copy", info)
    assert not (source.script_path.parent / "copy").exists()


def test_missing_source_is_reported_by_management(main_window, source, errors):
    ct = main_window.controller
    ct.load_plugin_path(source.config_path)
    source.script_path.unlink()
    manager = PluginManagerDlg(main_window, ct)
    manager._edit_plugin("edit_fixture")
    assert errors == ["Could not edit the plugin."]
    assert not _editors(manager)
    manager.close()


def test_copy_cancellation_leaves_registration_unchanged(
    main_window, source, monkeypatch
):
    ct = main_window.controller
    ct.load_plugin_path(source.config_path)
    original_meta = ct.get("plugin_meta")["edit_fixture"].copy()
    original_source = get_plugin_source(original_meta)
    monkeypatch.setattr(
        "mne_nodes.gui.parameter.plugin_manager.get_plugin_source",
        lambda *args: replace(original_source, installed=True),
    )
    monkeypatch.setattr(
        "mne_nodes.gui.parameter.plugin_manager.ask_user", lambda *args, **kwargs: False
    )
    manager = PluginManagerDlg(main_window, ct)
    manager._edit_plugin("edit_fixture")
    assert not _editors(manager)
    assert ct.get("plugin_meta")["edit_fixture"] == original_meta
    manager.close()


def test_config_install_cancellation_does_not_load_or_install(
    main_window, source, monkeypatch
):
    class Choice(LocalPluginInstallDialog):
        def exec(self):
            return QDialog.DialogCode.Rejected

    calls = []
    monkeypatch.setattr("mne_nodes.gui.main_window.LocalPluginInstallDialog", Choice)
    monkeypatch.setattr(
        "mne_nodes.gui.main_window.get_user_input",
        lambda *args, **kwargs: source.config_path,
    )
    monkeypatch.setattr(
        "mne_nodes.gui.main_window.install_local_plugin",
        lambda *a, **k: calls.append(True),
    )
    main_window.load_plugin_path()
    assert not calls
    assert "edit_fixture" not in main_window.controller.plugins


@pytest.mark.parametrize("editable", [True, False])
def test_load_config_path_exposes_installation_choice(
    main_window, source, monkeypatch, editable
):
    class Choice(LocalPluginInstallDialog):
        def exec(self):
            self.install_package.setChecked(True)
            self.editable_install.setChecked(editable)
            return QDialog.DialogCode.Accepted

    calls = []
    monkeypatch.setattr("mne_nodes.gui.main_window.LocalPluginInstallDialog", Choice)
    monkeypatch.setattr(
        "mne_nodes.gui.main_window.get_user_input",
        lambda *args, **kwargs: source.config_path,
    )
    monkeypatch.setattr(
        "mne_nodes.gui.main_window.install_local_plugin",
        lambda root, **kwargs: calls.append((root, kwargs["editable"])),
    )
    main_window.load_plugin_path()
    assert calls == [(source.project_root.resolve(), editable)]
    assert "edit_fixture" in main_window.controller.plugins
