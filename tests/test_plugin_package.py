"""Distribution-ready saving and installed-plugin discovery/management."""

import json
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from dataclasses import replace
from pathlib import Path
from types import ModuleType

import pytest
from build import ProjectBuilder
from packaging.metadata import Metadata
from qtpy.QtGui import QAction
from qtpy.QtWidgets import QDialog, QFrame, QLabel, QPushButton

from mne_nodes.backend.controller import Controller
from mne_nodes.backend.package_utils import (
    find_plugin_entry_point,
    get_import_name,
    get_plugin_entry_points,
)
from mne_nodes.backend.plugin_package import (
    PluginPackageMetadata,
    create_plugin_package,
    get_plugin_source,
)
from mne_nodes.gui.parameter.plugin_manager import PluginManagerDlg
from mne_nodes.gui.plugin_package import PluginPackageDialog

CODE = "def transform(value, scale=2):\n    return value * scale\n"
CONFIG = {
    "transform": {"inputs": {}, "outputs": {}, "parameters": {}, "target": "file"}
}


@pytest.fixture
def package_metadata():
    return PluginPackageMetadata(
        distribution_name="mne-nodes_packaging-fixture",
        description='A plugin with "quoted" metadata.',
        author="Test contributors",
        author_email="test@example.org",
        repository_url="https://example.org/plugins",
        license_expression="BSD-3-Clause",
        dependencies=("mne>=1.10",),
    )


def _register(monkeypatch, tmp_path, distribution_name, entry_name, module_name):
    """Make a real importlib EntryPoint backed by temporary dist-info."""
    dist_info = tmp_path / f"{distribution_name.replace('-', '_')}-0.1.0.dist-info"
    dist_info.mkdir()
    (dist_info / "METADATA").write_text(
        f"Metadata-Version: 2.4\nName: {distribution_name}\nVersion: 0.1.0\n",
        encoding="utf-8",
    )
    (dist_info / "entry_points.txt").write_text(
        f"[mne_nodes.plugins]\n{entry_name} = {module_name}\n", encoding="utf-8"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    return find_plugin_entry_point(distribution_name, entry_name)


@pytest.mark.parametrize(
    "changes",
    [
        {"distribution_name": "invalid name"},
        {"version": "not-a-version"},
        {"description": ""},
        {"author": ""},
        {"license_expression": ""},
        {"license_expression": "not-an-spdx-license"},
        {"license_expression": "Apache-2.0", "license_text": ""},
        {"dependencies": ("not a requirement?",)},
        {"dependencies": ("example @ https://example.org/package.whl",)},
    ],
)
def test_invalid_metadata_does_not_create_files(tmp_path, package_metadata, changes):
    before = set(tmp_path.iterdir())
    with pytest.raises(ValueError):
        create_plugin_package(
            tmp_path,
            "packaging_fixture",
            CODE,
            CONFIG,
            replace(package_metadata, **changes),
        )
    assert set(tmp_path.iterdir()) == before


@pytest.mark.parametrize("license_expression", ["BSD-3-Clause", "MIT", "Apache-2.0"])
def test_project_metadata_and_resources(tmp_path, package_metadata, license_expression):
    info = replace(
        package_metadata,
        license_expression=license_expression,
        license_text="Custom license text"
        if license_expression == "Apache-2.0"
        else "",
    )
    config = create_plugin_package(tmp_path, "packaging_fixture", CODE, CONFIG, info)
    project = tomllib.loads((tmp_path / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["name"] == info.distribution_name
    assert project["project"]["version"] == "0.1.0"
    assert project["project"]["description"] == info.description
    assert project["project"]["license"] == license_expression
    assert project["project"]["license-files"] == ["LICENSE"]
    assert project["project"]["dependencies"] == ["mne-nodes", "mne>=1.10"]
    assert project["project"]["entry-points"]["mne_nodes.plugins"] == {
        "packaging_fixture": "mne_nodes_packaging_fixture"
    }
    assert json.loads(config.read_text(encoding="utf-8")) == CONFIG
    assert (
        config.parent.joinpath("packaging_fixture.py").read_text(encoding="utf-8")
        == CODE
    )
    assert (
        "Custom license text" in (tmp_path / "LICENSE").read_text()
        if (license_expression == "Apache-2.0")
        else info.author in (tmp_path / "LICENSE").read_text()
    )


@pytest.mark.parametrize(
    "conflict", ["pyproject.toml", "README.md", "LICENSE", ".gitignore"]
)
def test_existing_project_is_never_overwritten(tmp_path, package_metadata, conflict):
    original = tmp_path / conflict
    original.write_text("original", encoding="utf-8")
    before = set(tmp_path.iterdir())
    with pytest.raises(FileExistsError):
        create_plugin_package(
            tmp_path, "packaging_fixture", CODE, CONFIG, package_metadata
        )
    assert original.read_text() == "original"
    assert set(tmp_path.iterdir()) == before


def test_package_build_install_and_entry_point_round_trip(
    ct, tmp_path, package_metadata, monkeypatch
):
    """Build from an sdist without Git, install a wheel and run its plugin."""
    source = tmp_path / "source"
    create_plugin_package(source, "packaging_fixture", CODE, CONFIG, package_metadata)
    artifacts = tmp_path / "dist"
    sdist = Path(ProjectBuilder(str(source)).build("sdist", str(artifacts)))
    unpacked = tmp_path / "unpacked"
    with tarfile.open(sdist) as archive:
        archive.extractall(unpacked, filter="data")
    (archive_root,) = unpacked.iterdir()
    sdist_metadata = Metadata.from_email((archive_root / "PKG-INFO").read_bytes())
    wheel = Path(ProjectBuilder(str(archive_root)).build("wheel", str(artifacts)))
    with zipfile.ZipFile(wheel) as archive:
        assert (
            "mne_nodes_packaging_fixture/packaging_fixture_config.json"
            in archive.namelist()
        )
        assert any(
            name.endswith(".dist-info/licenses/LICENSE") for name in archive.namelist()
        )
        wheel_metadata = archive.read(
            next(
                name
                for name in archive.namelist()
                if name.endswith(".dist-info/METADATA")
            )
        ).decode()
        assert "License-Expression: BSD-3-Clause" in wheel_metadata
        assert "Requires-Dist: mne-nodes" in wheel_metadata
        assert Metadata.from_email(wheel_metadata).version == sdist_metadata.version
    target = tmp_path / "installed"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--target",
            str(target),
            str(wheel),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    monkeypatch.syspath_prepend(str(target))
    module_name = "mne_nodes_packaging_fixture"
    assert module_name not in sys.modules
    registrations = get_plugin_entry_points()
    assert any(entry.name == "packaging_fixture" for entry in registrations)
    assert module_name not in sys.modules
    assert get_import_name(package_metadata.distribution_name) == module_name
    monkeypatch.setitem(sys.modules, module_name, None)
    sys.modules.pop(module_name)
    monkeypatch.setitem(sys.modules, f"{module_name}.packaging_fixture", None)
    sys.modules.pop(f"{module_name}.packaging_fixture")
    ct.load_plugin_entry_point(package_metadata.distribution_name, "packaging_fixture")
    plugin = ct.plugins["packaging_fixture"]
    assert plugin.transform(3) == 6
    saved_meta = ct.get("plugin_meta")["packaging_fixture"]
    assert saved_meta["plugin_type"] == "entry_point"
    assert saved_meta["distribution_name"] == package_metadata.distribution_name
    assert saved_meta["entry_point_name"] == "packaging_fixture"
    assert get_plugin_source(saved_meta).installed
    ct.reload_plugins("packaging_fixture")
    assert ct.plugins["packaging_fixture"] is not plugin
    assert ct.plugins["packaging_fixture"].transform(3) == 6
    ct.disable_plugin("packaging_fixture")
    assert "packaging_fixture" not in ct.plugins
    ct.enable_plugin("packaging_fixture")
    assert ct.plugins["packaging_fixture"].transform(4) == 8
    ct.remove_plugin("packaging_fixture")
    ct.set_dict_value("plugin_meta", "packaging_fixture", saved_meta)
    ct.load_recent_plugins()
    assert ct.plugins["packaging_fixture"].transform(5) == 10


def test_entry_point_identity_and_no_eager_import(tmp_path, monkeypatch):
    first = _register(monkeypatch, tmp_path, "first-dist", "shared", "first_module")
    second = _register(monkeypatch, tmp_path, "second-dist", "shared", "second_module")
    assert first.module == "first_module"
    assert second.module == "second_module"
    assert first.module not in sys.modules
    assert second.module not in sys.modules
    assert find_plugin_entry_point("FIRST_dist", "shared").module == "first_module"
    with pytest.raises(LookupError, match="found 0"):
        find_plugin_entry_point("absent", "shared")


def test_broken_entry_point_does_not_register_plugin(ct, tmp_path, monkeypatch):
    _register(
        monkeypatch, tmp_path, "broken-dist", "broken", "missing_test_plugin_module"
    )
    before = ct.get("plugin_meta").copy()
    with pytest.raises(ModuleNotFoundError):
        ct.load_plugin_entry_point("broken-dist", "broken")
    assert ct.get("plugin_meta") == before


@pytest.fixture
def installed_entry(tmp_path, monkeypatch):
    """Provide one real registration, without involving machine-installed plugins."""
    config = tmp_path / "discovery_plugin_config.json"
    config.write_text(json.dumps(CONFIG), encoding="utf-8")
    (tmp_path / "discovery_plugin.py").write_text(
        "from pathlib import Path\n"
        "PLUGIN_NAME = 'discovered'\n"
        f"CONFIG_PATH = Path({str(config)!r})\n"
        "def transform(value):\n    return value * 2\n",
        encoding="utf-8",
    )
    entry = _register(
        monkeypatch, tmp_path, "discovered-dist", "discovery-entry", "discovery_plugin"
    )
    monkeypatch.delitem(sys.modules, "discovery_plugin", raising=False)
    monkeypatch.setattr(
        "mne_nodes.backend.controller.get_plugin_entry_points", lambda: [entry]
    )
    yield entry
    sys.modules.pop("discovery_plugin", None)


def test_new_installed_plugin_enabled_at_startup(settings, installed_entry):
    controller = Controller(settings=settings)
    assert controller.plugins["discovered"].transform(3) == 6
    meta = controller.get("plugin_meta")["discovered"]
    assert meta["distribution_name"] == "discovered-dist"
    assert meta["entry_point_name"] == "discovery-entry"
    assert controller.plugin_node_count("discovered") == 1
    controller.disable_plugin("discovered")
    restarted = Controller(settings=settings)
    assert "discovered" not in restarted.plugins
    assert "discovered" in restarted.get("plugin_meta")
    assert restarted.plugin_node_count("discovered") == 1


def test_discovery_preserves_path_registration(ct, installed_entry):
    ct.load_plugin_path(Path(sys.path[0]) / "discovery_plugin_config.json")
    original = ct.get("plugin_meta")["discovered"].copy()
    ct.discover_installed_plugins()
    assert ct.get("plugin_meta")["discovered"] == original


def test_discovery_errors_visible_without_blocking_healthy_plugins(
    ct, installed_entry, tmp_path, monkeypatch, qtbot
):
    broken = _register(
        monkeypatch, tmp_path, "broken-dist", "broken-entry", "missing_plugin_code"
    )
    monkeypatch.setattr(
        "mne_nodes.backend.controller.get_plugin_entry_points",
        lambda: [broken, installed_entry],
    )
    manager = PluginManagerDlg(None, ct)
    qtbot.addWidget(manager)
    assert "discovered" in ct.plugins
    assert (
        "ModuleNotFoundError"
        in ct.installed_plugins["broken-dist:broken-entry"]["error"]
    )
    assert any(
        "ModuleNotFoundError" in label.text() for label in manager.findChildren(QLabel)
    )


def test_registered_installed_plugin_failure_does_not_block_startup(
    ct, installed_entry, monkeypatch, qtbot
):
    ct.load_plugin_entry_point("discovered-dist", "discovery-entry")
    ct.flush()

    def broken(*args):
        raise ImportError("Plugin dependency missing")

    monkeypatch.setattr(Controller, "load_plugin_entry_point", broken)
    restarted = Controller(config_path=ct.config_path, settings=ct.settings)
    assert "discovered" not in restarted.plugins
    assert (
        "Plugin dependency missing"
        in restarted.installed_plugins["discovered-dist:discovery-entry"]["error"]
    )
    manager = PluginManagerDlg(None, restarted)
    qtbot.addWidget(manager)
    group = next(
        group
        for group in manager.findChildren(QFrame, "plugin_card")
        if group.property("plugin_name") == "discovered"
    )
    assert group.findChild(QLabel, "plugin_status").text() == "error"


def test_failed_enable_keeps_disabled_choice(ct, installed_entry, monkeypatch):
    ct.discover_installed_plugins()
    ct.disable_plugin("discovered")

    def broken(name):
        raise ImportError("Plugin dependency missing")

    monkeypatch.setattr(ct, "load_recent_plugins", broken)
    with pytest.raises(ImportError, match="Plugin dependency missing"):
        ct.enable_plugin("discovered")
    assert "discovered" in ct.settings.get("disabled_plugins")


def test_entry_point_must_reference_module(ct, tmp_path, monkeypatch):
    (tmp_path / "nonmodule_plugin.py").write_text("VALUE = 42\n", encoding="utf-8")
    _register(
        monkeypatch, tmp_path, "nonmodule-dist", "nonmodule", "nonmodule_plugin:VALUE"
    )
    monkeypatch.setitem(sys.modules, "nonmodule_plugin", None)
    sys.modules.pop("nonmodule_plugin")
    with pytest.raises(TypeError, match="must reference a module"):
        ct.load_plugin_entry_point("nonmodule-dist", "nonmodule")
    assert "nonmodule" not in ct.plugins


def test_module_plugin_reload_uses_import_name(ct, tmp_path, monkeypatch):
    plugin = ModuleType("test_import_module_name")
    config_path = tmp_path / "display_config.json"
    config_path.write_text(json.dumps(CONFIG), encoding="utf-8")
    plugin.__dict__.update(
        PLUGIN_NAME="display-name",
        CONFIG_PATH=config_path,
        PLUGIN_GITHUB="https://github.com/example/package",
        transform=lambda value: value,
    )
    monkeypatch.setitem(sys.modules, plugin.__name__, plugin)
    ct.load_plugin_module(plugin)
    assert ct.get("plugin_meta")["display-name"]["plugin_type"] == "module"
    ct.load_recent_plugins("display-name")
    assert ct.plugins["display-name"] is plugin


def test_local_package_relative_imports_and_reload(ct, tmp_path, package_metadata):
    config = create_plugin_package(
        tmp_path,
        "relative_fixture",
        "from .helper import scale\n\ndef transform(value):\n    return scale(value)\n",
        CONFIG,
        package_metadata,
    )
    helper = config.parent / "helper.py"
    helper.write_text("def scale(value):\n    return value * 2\n", encoding="utf-8")
    ct.load_plugin_path(config)
    assert ct.plugins["relative_fixture"].transform(3) == 6
    helper.write_text("def scale(value):\n    return value * 7\n", encoding="utf-8")
    ct.load_plugin_path(config)
    assert ct.plugins["relative_fixture"].transform(3) == 21
    previous = ct.plugins["relative_fixture"]
    helper.write_text("raise RuntimeError('broken update')\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="broken update"):
        ct.load_plugin_path(config)
    assert ct.plugins["relative_fixture"] is previous
    assert sys.modules[previous.__name__] is previous


def test_metadata_dialog_requires_explicit_license(qtbot, monkeypatch):
    errors = []
    monkeypatch.setattr(
        "mne_nodes.gui.plugin_package.ErrorDialog.open",
        lambda self: errors.append(self),
    )
    dialog = PluginPackageDialog("my_plugin")
    qtbot.addWidget(dialog)
    dialog.description.setText("My plugin")
    dialog.author.setText("Plugin contributors")
    dialog.accept()
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog.metadata is None
    assert len(errors) == 1
    dialog.license_choice.setCurrentText("MIT")
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.metadata is not None
    assert dialog.metadata.license_expression == "MIT"


def test_manager_discovers_external_install_and_preserves_disable(
    main_window, installed_entry, qtbot
):
    ct = main_window.controller
    manager = PluginManagerDlg(main_window, ct)
    assert "discovered" in ct.plugins

    def row():
        return next(
            group
            for group in manager.findChildren(QFrame, "plugin_card")
            if group.property("plugin_name") == "discovered" and group.isVisible()
        )

    group = row()
    enabled_color = group.findChild(QLabel, "plugin_status").styleSheet()
    assert "white" not in enabled_color
    assert group.findChild(QLabel, "plugin_status").text() == "enabled"
    assert group.findChild(QLabel, "plugin_node_count").text() == "Nodes: 1"
    next(
        button
        for button in group.findChildren(QPushButton)
        if button.text() == "Disable"
    ).click()
    qtbot.wait(1)
    group = row()
    assert "discovered" not in ct.plugins
    assert group.findChild(QLabel, "plugin_status").text() == "disabled"
    assert group.findChild(QLabel, "plugin_status").styleSheet() != enabled_color
    assert group.findChild(QLabel, "plugin_node_count").text() == "Nodes: 1"
    manager._discover_plugins()
    assert "discovered" not in ct.plugins
    manager.close()
    reopened = PluginManagerDlg(main_window, ct)
    assert "discovered" not in ct.plugins
    reopened._toggle_plugin("discovered", True)
    assert ct.plugins["discovered"].transform(2) == 4
    reopened.close()


def test_manager_refresh_finds_plugin_installed_while_open(
    ct, installed_entry, monkeypatch, qtbot
):
    monkeypatch.setattr("mne_nodes.backend.controller.get_plugin_entry_points", list)
    manager = PluginManagerDlg(None, ct)
    qtbot.addWidget(manager)
    assert "discovered" not in ct.plugins
    monkeypatch.setattr(
        "mne_nodes.backend.controller.get_plugin_entry_points",
        lambda: [installed_entry],
    )
    manager._discover_plugins()
    assert "discovered" in ct.plugins
    assert (
        len(
            [
                record
                for record in ct.installed_plugins.values()
                if record.get("plugin_name") == "discovered"
            ]
        )
        == 1
    )


def test_installed_picker_removed_from_menu(main_window):
    assert not hasattr(main_window, "load_installed_plugin")
    assert all(
        action.text() != "Load Installed Plugin..."
        for action in main_window.findChildren(QAction)
    )
