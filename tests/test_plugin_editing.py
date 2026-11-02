"""Safe editing, optional installation and Git initialization of plugins."""

import json
import shutil
import subprocess
import sys
from dataclasses import replace

import pytest
from qtpy.QtWidgets import QDialog, QPushButton

from mne_nodes.backend.package_utils import (
    install_github_package,
    install_local_plugin,
    install_pip_packages,
    uninstall_pip_packages,
)
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
from mne_nodes.gui.plugin_package import LocalPluginInstallDialog
from mne_nodes.gui.run_widgets import ProcessDialog

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


@pytest.mark.skipif(shutil.which("git") is None, reason="Git is unavailable")
def test_git_initialization(tmp_path, info):
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
    # Invalid branch names are rejected before any file is written.
    for branch in ["", "--bad", "bad..branch", "two words"]:
        with pytest.raises(ValueError, match="branch"):
            create_plugin_package(
                tmp_path / "project",
                "git_fixture",
                CODE,
                CONFIG,
                replace(info, initialize_git=True, initial_branch=branch),
            )
        assert not (tmp_path / "project").exists()


def test_failed_post_save_steps_keep_files_and_can_be_retried(
    qtbot, tmp_path, source, info, monkeypatch, errors
):
    calls = []

    def flaky(*args):
        calls.append(args)
        if len(calls) % 2:
            raise RuntimeError("Simulated failure")

    # Git initialization of a new package fails once.
    monkeypatch.setattr(
        "mne_nodes.gui.function_widgets.initialize_plugin_repository", flaky
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
    assert importer.save()
    importer.func_config.clear()
    importer.close()

    # Reloading an edited plugin fails once.
    editor = FunctionImporter(source=source, on_saved=flaky)
    qtbot.addWidget(editor)
    editor.source_editor.setPlainText(CODE.replace("scale=2", "scale=4"))
    assert not editor.save()
    assert "scale=4" in source.script_path.read_text(encoding="utf-8")
    assert editor.save()
    assert len(calls) == 4
    assert len(errors) == 2
    editor.close()


@pytest.mark.parametrize("editable", [True, False])
def test_local_installation_mode(qtbot, tmp_path, source, info, monkeypatch, editable):
    pip_calls = []
    monkeypatch.setattr(
        "mne_nodes.backend.package_utils.install_pip_packages",
        lambda arguments, **kwargs: pip_calls.append(arguments),
    )
    install_local_plugin(source.project_root, editable=editable)
    expected = [str(source.project_root.resolve())]
    if editable:
        expected.insert(0, "--editable")
    assert pip_calls == [expected]

    # Saving a new package installs it once, only when requested.
    calls = []
    monkeypatch.setattr(
        "mne_nodes.gui.function_widgets.install_local_plugin",
        lambda root, **kwargs: calls.append((root, kwargs["editable"])),
    )
    importer = FunctionImporter(
        code=CODE,
        plugin_name="install_fixture",
        destination_dir=tmp_path / "project",
        package_metadata=replace(info, install_package=True, editable_install=editable),
    )
    qtbot.addWidget(importer)
    assert importer.save()
    assert importer.save()
    assert calls == [(tmp_path / "project", editable)]
    importer.func_config.clear()
    importer.close()


@pytest.mark.parametrize("exit_code", [0, 7])
@pytest.mark.parametrize("kind", ["pip", "github", "local", "uninstall"])
def test_install_result_after_process_cleanup(
    qtbot, monkeypatch, tmp_path, kind, exit_code
):
    """Installation results remain available after Qt deletes the process."""

    def run_test_command(**kwargs):
        if kind == "uninstall":
            assert kwargs["commands"] == [
                (sys.executable, "-m", "pip", "uninstall", "-y", "example-plugin")
            ]
        kwargs["commands"] = [
            (sys.executable, "-c", f"import sys; sys.exit({exit_code})")
        ]
        kwargs["blocking"] = False
        dialog = ProcessDialog(**kwargs)
        qtbot.addWidget(dialog)
        with qtbot.waitSignal(dialog.process.destroyed, timeout=5000):
            pass
        dialog.close()
        return dialog

    monkeypatch.setattr(
        "mne_nodes.backend.package_utils.ProcessDialog", run_test_command
    )
    if kind == "local":
        (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")

    def install():
        if kind == "github":
            return install_github_package("https://github.com/owner/plugin")
        if kind == "local":
            return install_local_plugin(tmp_path)
        if kind == "uninstall":
            return uninstall_pip_packages(["example-plugin"])
        return install_pip_packages(["example-plugin"])

    if exit_code:
        operation = "uninstallation" if kind == "uninstall" else "installation"
        with pytest.raises(
            RuntimeError, match=f"{operation} failed with exit code {exit_code}"
        ):
            install()
    else:
        dialog = install()
        assert dialog.exit_code == 0


def test_uninstall_requires_package_names():
    """An empty request must not launch pip."""
    with pytest.raises(ValueError, match="No package names"):
        uninstall_pip_packages([])


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


@pytest.mark.parametrize("disabled", [False, True])
def test_edit_local_plugin_saves_and_reloads(main_window, source, errors, disabled):
    ct = main_window.controller
    ct.load_plugin_path(source.config_path)
    if disabled:
        ct.disable_plugin("edit_fixture")
    original_meta = ct.get("plugin_meta")["edit_fixture"].copy()
    manager = PluginManagerDlg(main_window, ct)
    manager._edit_plugin("edit_fixture")
    (editor,) = _editors(manager)
    editor.source_editor.setPlainText(CODE.replace("scale=2", "scale=8"))
    assert editor.save()
    editor.close()
    assert "scale=8" in source.script_path.read_text(encoding="utf-8")
    assert ct.get("plugin_meta")["edit_fixture"] == original_meta
    if disabled:
        assert "edit_fixture" not in ct.plugins
        assert "edit_fixture" in ct.settings.get("disabled_plugins")
    else:
        assert ct.plugins["edit_fixture"].transform(2) == 16
    # A missing source is reported instead of opening an editor.
    open_editors = len(_editors(manager))
    source.script_path.unlink()
    manager._edit_plugin("edit_fixture")
    assert len(errors) == 1
    assert len(_editors(manager)) == open_editors
    manager.close()


@pytest.mark.parametrize("installed", [False, True])
def test_manager_edit_action_matches_source(
    main_window, source, monkeypatch, installed
):
    """Only local/editable source has a direct Edit action."""
    ct = main_window.controller
    ct.load_plugin_path(source.config_path)
    monkeypatch.setattr(
        "mne_nodes.gui.parameter.plugin_manager.get_plugin_source",
        lambda *args: replace(source, installed=installed),
    )
    manager = PluginManagerDlg(main_window, ct)
    card = manager._make_row(
        "edit_fixture", ct.get("plugin_meta")["edit_fixture"], False
    )
    buttons = {button.text(): button for button in card.findChildren(QPushButton)}
    assert buttons["Edit..."].isEnabled() is not installed
    assert ("Copy to edit..." in buttons) is installed
    source.script_path.unlink()
    monkeypatch.setattr(
        "mne_nodes.gui.parameter.plugin_manager.get_plugin_source", get_plugin_source
    )
    unavailable = manager._make_row(
        "edit_fixture", ct.get("plugin_meta")["edit_fixture"], False
    )
    edit = next(
        button
        for button in unavailable.findChildren(QPushButton)
        if button.text() == "Edit..."
    )
    assert not edit.isEnabled()
    assert "missing" in edit.toolTip()
    card.deleteLater()
    unavailable.deleteLater()
    manager.close()


@pytest.mark.parametrize("outcome", ["success", "cancel", "failure"])
@pytest.mark.parametrize(
    "registration", ["entry_point", "installed_path", "local_path", "broken"]
)
def test_manager_uninstalls_installed_distribution(
    main_window, source, monkeypatch, errors, outcome, registration
):
    """Uninstall is available for installed plugins, including failed imports."""
    ct = main_window.controller
    broken = registration == "broken"
    if not broken:
        ct.load_plugin_path(source.config_path)
        meta = ct.get("plugin_meta")["edit_fixture"]
        ct.set_dict_value(
            "plugin_meta",
            "edit_fixture",
            {
                **meta,
                "plugin_type": "entry_point"
                if registration == "entry_point"
                else "path",
            },
        )
    monkeypatch.setattr(
        "mne_nodes.gui.parameter.plugin_manager.plugin_source_is_installed",
        lambda path: registration == "installed_path",
    )
    record = {
        "distribution_name": "mne-nodes_edit-fixture",
        "entry_point_name": "edit_fixture",
        "module_name": "mne_nodes_edit_fixture",
        "version": "0.1.0",
    }
    if broken:
        record["error"] = "Import failed"
    else:
        record["plugin_name"] = "edit_fixture"
    identity = "mne-nodes-edit-fixture:edit_fixture"
    ct.installed_plugins = {identity: record}
    monkeypatch.setattr(ct, "discover_installed_plugins", lambda: None)
    questions = []

    def confirm(question, **kwargs):
        questions.append(question)
        return outcome != "cancel"

    monkeypatch.setattr("mne_nodes.gui.parameter.plugin_manager.ask_user", confirm)
    calls = []

    def uninstall(packages, **kwargs):
        calls.append(packages)
        if outcome == "failure":
            raise RuntimeError("pip failed")

    monkeypatch.setattr(
        "mne_nodes.gui.parameter.plugin_manager.uninstall_pip_packages", uninstall
    )
    manager = PluginManagerDlg(main_window, ct)
    card = manager._rows_layout.itemAt(manager._rows_layout.count() - 1).widget()
    buttons = {button.text(): button for button in card.findChildren(QPushButton)}
    assert buttons["Uninstall..."].isEnabled()
    if not broken:
        assert not buttons["Remove"].isEnabled()
    buttons["Uninstall..."].click()
    assert len(questions) == 1
    assert record["distribution_name"] in questions[0]
    assert calls == ([] if outcome == "cancel" else [[record["distribution_name"]]])
    assert len(errors) == (1 if outcome == "failure" else 0)
    assert (identity in ct.installed_plugins) is (outcome != "success")
    if not broken:
        retained = outcome != "success" or registration == "local_path"
        assert ("edit_fixture" in ct.plugins) is retained
        assert ("edit_fixture" in ct.get("plugin_meta")) is retained
    assert source.script_path.is_file()
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


def test_editor_saves_source_configuration_and_package_files(qtbot, source):
    original_config = source.config_path.read_bytes()
    project = source.project_root / "pyproject.toml"
    readme = source.project_root / "README.md"
    editor = FunctionImporter(source=source)
    qtbot.addWidget(editor)
    assert editor.save()
    assert source.config_path.read_bytes() == original_config
    editor.package_editors[project].setPlainText(
        project.read_text(encoding="utf-8").replace(
            'version = "0.1.0"', 'version = "0.2.0"'
        )
    )
    editor.package_editors[readme].setPlainText("Updated README\n")
    assert editor.save()
    assert 'version = "0.2.0"' in project.read_text(encoding="utf-8")
    assert readme.read_text() == "Updated README\n"
    assert source.script_path.read_text(encoding="utf-8") == CODE
    editor.source_editor.setPlainText(CODE.replace("scale=2", "scale=7"))
    editor.reanalyze()
    assert editor.func_config["transform"]["parameters"]["scale"]["default"] == 7
    assert editor.save()
    assert json.loads(source.config_path.read_text()) == editor.func_config
    editor.close()


@pytest.mark.parametrize("local_code", ["", CODE.replace("transform", "renamed")])
def test_editor_keeps_imported_function_configuration(qtbot, source, ct, local_code):
    source.script_path.write_text(
        "from math import sqrt\nsquare_root = sqrt\n" + local_code, encoding="utf-8"
    )
    config = {
        name: json.loads(json.dumps(CONFIG["transform"]))
        for name in ("sqrt", "square_root", "transform", "renamed")
    }
    config["cos"] = {**CONFIG["transform"], "module_name": "math"}
    config["upper"] = {
        **CONFIG["transform"],
        "module_name": "builtins",
        "class_name": "str",
    }
    source.config_path.write_text(json.dumps(config))
    editor = FunctionImporter(source=source)
    qtbot.addWidget(editor)
    editor.reanalyze()
    expected = {"sqrt", "square_root", "cos", "upper"}
    if local_code:
        expected.add("renamed")
    assert set(editor.func_config) == expected
    editor.function_cmbx.setCurrentText("sqrt")
    assert editor.current_func == "sqrt"
    editor.func_config["sqrt"]["target"] = "group"
    assert editor.save()
    assert json.loads(source.config_path.read_text())["sqrt"]["target"] == "group"
    ct.load_plugin_path(source.config_path)
    assert set(ct.get_func_by_input("value")) >= expected
    assert "transform" not in ct.get_func_by_input("value")
    editor.close()


@pytest.mark.parametrize("invalid", ["source", "json", "toml", "external"])
def test_editor_writes_nothing_when_invalid_or_changed_externally(
    qtbot, source, errors, invalid
):
    project = source.project_root / "pyproject.toml"
    editor = FunctionImporter(source=source)
    qtbot.addWidget(editor)
    editor.source_editor.setPlainText(CODE.replace("scale=2", "scale=5"))
    if invalid == "source":
        editor.source_editor.setPlainText("def broken(:")
    elif invalid == "json":
        editor.func_config["transform"] = []
    elif invalid == "toml":
        editor.package_editors[project].setPlainText("[broken")
    else:
        source.script_path.write_text("# external edit\n" + CODE, encoding="utf-8")
    originals = {
        path: path.read_bytes()
        for path in (source.script_path, source.config_path, project)
    }
    assert not editor.save()
    assert len(errors) == 1
    assert all(path.read_bytes() == text for path, text in originals.items())
    editor._original.update(editor._existing_plugin_contents())
    editor.close()


def test_installed_sources_are_protected(qtbot, source, info, monkeypatch):
    with pytest.raises(ValueError, match="outside"):
        copy_plugin_source(source, source.script_path.parent / "copy", info)
    assert not (source.script_path.parent / "copy").exists()

    # Files inside the Python environment are never edited in place.
    with monkeypatch.context() as patch:
        patch.setattr(
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

    # Distribution files are protected unless installed as editable.
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
    original_meta = ct.get("plugin_meta")["edit_fixture"].copy()
    original_source = get_plugin_source(original_meta)
    monkeypatch.setattr(
        "mne_nodes.gui.parameter.plugin_manager.get_plugin_source",
        lambda *args: replace(original_source, installed=True),
    )
    manager = PluginManagerDlg(main_window, ct)

    # Cancelling the copy leaves the registration unchanged.
    monkeypatch.setattr(
        "mne_nodes.gui.parameter.plugin_manager.ask_user", lambda *args, **kwargs: False
    )
    manager._edit_plugin("edit_fixture")
    assert not _editors(manager)
    assert ct.get("plugin_meta")["edit_fixture"] == original_meta

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


@pytest.mark.parametrize("editable", [None, True, False])
def test_load_config_path_installation_choice(
    main_window, source, monkeypatch, editable
):
    class Choice(LocalPluginInstallDialog):
        def exec(self):
            if editable is None:
                return QDialog.DialogCode.Rejected
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
    if editable is None:
        assert not calls
        assert "edit_fixture" not in main_window.controller.plugins
    else:
        assert calls == [(source.project_root.resolve(), editable)]
        assert "edit_fixture" in main_window.controller.plugins
