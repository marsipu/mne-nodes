"""Saving, loading and error handling of custom function imports."""

import json

import pytest
from qtpy.QtCore import QMimeData, QPointF, Qt, QUrl
from qtpy.QtGui import QDropEvent

from mne_nodes.backend.plugin_package import PluginPackageMetadata
from mne_nodes.gui.function_widgets import FunctionImporter
from mne_nodes.gui.gui_utils import is_function_import_mime

CODE = "def transform(raw, scale=2):\n    result = raw * scale\n    return result\n"


@pytest.fixture
def importer_input(monkeypatch, tmp_path):
    """Supply a stable plugin name and destination without interactive prompts."""
    calls = []

    def user_input(prompt, input_type="string", **kwargs):
        calls.append(input_type)
        return tmp_path if input_type == "folder" else "custom_functions"

    monkeypatch.setattr("mne_nodes.gui.function_widgets.get_user_input", user_input)
    monkeypatch.setattr(
        "mne_nodes.gui.function_widgets.request_package_metadata",
        lambda *args: PluginPackageMetadata(
            distribution_name="mne-nodes_custom-functions",
            description="Test plugin",
            author="Test contributors",
            license_expression="BSD-3-Clause",
        ),
    )
    return calls


@pytest.fixture
def errors(monkeypatch):
    captured = []
    monkeypatch.setattr(
        "mne_nodes.gui.function_widgets.ErrorDialog.open",
        lambda self: captured.append(self),
    )
    return captured


def _package_dir(root, plugin_name="custom_functions"):
    return root / "src" / f"mne_nodes_{plugin_name}"


def _importers(main_window):
    return main_window.findChildren(FunctionImporter)


def _discard_importers(main_window):
    for importer in _importers(main_window):
        # Avoid unsaved-change prompts during fixture cleanup.
        importer.func_config.clear()
        importer.close()


@pytest.mark.parametrize(
    "code", ["not Python code!", "import math\n", "def broken(:\n"]
)
def test_bad_code_reports_error(main_window, monkeypatch, qtbot, code):
    errors = []

    class ErrorCapture:
        def __init__(self, exception_tuple, parent, title):
            errors.append(exception_tuple)

        def open(self):
            pass

    monkeypatch.setattr("mne_nodes.gui.main_window.ErrorDialog", ErrorCapture)
    main_window.import_functions(code=code)
    assert len(errors) == 1
    qtbot.waitUntil(lambda: not _importers(main_window))


@pytest.mark.parametrize(
    "url", ["https://example.org/plugin.py", "file:///C:/plugin.json"]
)
def test_non_python_urls_are_not_code(url):
    mime = QMimeData()
    mime.setUrls([QUrl(url)])
    mime.setText(url)
    assert not is_function_import_mime(mime)


def test_picker_drop_is_not_imported(main_window):
    mime = QMimeData()
    mime.setText("mne-nodes/function:test_filter")
    assert not is_function_import_mime(mime)
    count = len(main_window.viewer.nodes)
    event = QDropEvent(
        QPointF(20, 20),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    main_window.viewer.dropEvent(event)
    assert event.isAccepted()
    assert len(main_window.viewer.nodes) == count + 1
    assert not _importers(main_window)


def test_text_plugin_save_preserves_module(qtbot, importer_input, tmp_path):
    code = (
        "import math\n\n"
        "def decorate(func):\n    return func\n\n"
        "@decorate\n"
        "def transform(raw, scale=2):\n"
        "    result = math.sqrt(raw) * scale\n"
        "    return result\n\n"
        "# Module-level code must not run during analysis.\n"
        "raise RuntimeError('not executed')\n"
    )
    importer = FunctionImporter(code=code)
    qtbot.addWidget(importer)
    assert importer_input == ["string"]
    importer.editors["transform"].setPlainText(
        importer.editors["transform"].toPlainText().replace("scale=2", "scale=3")
    )
    importer.reanalyze()
    assert importer.func_config["transform"]["parameters"]["scale"]["default"] == 3
    importer.save()
    script_path = _package_dir(tmp_path) / "custom_functions.py"
    config_path = _package_dir(tmp_path) / "custom_functions_config.json"
    assert importer.file_path == script_path
    assert script_path.read_text(encoding="utf-8") == code.replace("scale=2", "scale=3")
    assert "transform" in json.loads(config_path.read_text(encoding="utf-8"))
    assert importer_input == ["string", "folder"]
    importer.func_config.clear()
    importer.close()


def test_invalid_reanalysis_preserves_editor(qtbot, importer_input, errors):
    importer = FunctionImporter(code=CODE)
    qtbot.addWidget(importer)
    editor = importer.editors["transform"]
    editor.setPlainText("def broken(:")
    importer.reanalyze()
    assert len(errors) == 1
    assert importer.editors["transform"] is editor
    assert editor.toPlainText() == "def broken(:"
    importer.func_config.clear()
    importer.close()


def test_file_import_never_modifies_source(qtbot, tmp_path, importer_input):
    script = tmp_path / "encoded.py"
    original = ("# coding: latin-1\n# caf\xe9\n" + CODE).encode("latin-1")
    script.write_bytes(original)
    importer = FunctionImporter(file_path=script)
    qtbot.addWidget(importer)
    assert "caf\xe9" in importer.get_code()
    importer.editors["transform"].setPlainText(
        importer.editors["transform"].toPlainText().replace("scale=2", "scale=7")
    )
    importer.reanalyze()
    assert importer.save()
    assert script.read_bytes() == original
    assert (_package_dir(tmp_path, "encoded") / "encoded_config.json").is_file()
    saved_code = importer.file_path.read_text(encoding="utf-8")
    assert "# coding: utf-8" in saved_code
    assert "caf\xe9" in saved_code
    assert "scale=7" in saved_code
    assert importer.func_config["transform"]["parameters"]["scale"]["default"] == 7
    # Re-saving keeps manually customized package metadata.
    metadata_file = tmp_path / "pyproject.toml"
    metadata_file.write_text("# manually customized metadata\n", encoding="utf-8")
    assert importer.save()
    assert (
        metadata_file.read_text(encoding="utf-8") == "# manually customized metadata\n"
    )
    importer.close()


def test_loading_another_file_chooses_a_new_package_destination(
    qtbot, importer_input, tmp_path, monkeypatch
):
    sources = [tmp_path / "first.py", tmp_path / "second.py"]
    destinations = [tmp_path / "first_package", tmp_path / "second_package"]
    for source in sources:
        source.write_text(CODE, encoding="utf-8")
    choices = iter(destinations)
    monkeypatch.setattr(
        "mne_nodes.gui.function_widgets.get_user_input",
        lambda *args, **kwargs: next(choices),
    )
    importer = FunctionImporter(file_path=sources[0])
    qtbot.addWidget(importer)
    assert importer.save()
    importer.load_file(sources[1])
    assert importer.save()
    for source, destination in zip(sources, destinations, strict=True):
        config = _package_dir(destination, source.stem) / f"{source.stem}_config.json"
        assert config.is_file()
        assert source.read_text(encoding="utf-8") == CODE
    importer.close()


@pytest.mark.parametrize("plugin_name", ["my-plugin", "two words", "1plugin", "class"])
@pytest.mark.parametrize("source", ["text", "file"])
def test_invalid_plugin_names_cannot_be_saved(
    qtbot, monkeypatch, tmp_path, errors, plugin_name, source
):
    if source == "text":
        monkeypatch.setattr(
            "mne_nodes.gui.function_widgets.get_user_input",
            lambda *args, **kwargs: plugin_name,
        )
        importer = FunctionImporter(code=CODE)
    else:
        path = tmp_path / f"{plugin_name}.py"
        path.write_text(CODE, encoding="utf-8")
        importer = FunctionImporter(file_path=path)
    qtbot.addWidget(importer)

    assert not importer.save()
    assert len(errors) == 1
    assert not list(tmp_path.glob("*_config.json"))
    importer.func_config.clear()
    importer.close()


@pytest.mark.parametrize("case", ["existing_file", "metadata_cancelled"])
def test_unsaved_new_plugin_writes_nothing(
    qtbot, importer_input, tmp_path, monkeypatch, errors, case
):
    if case == "existing_file":
        (tmp_path / "pyproject.toml").write_text("original", encoding="utf-8")
    else:
        monkeypatch.setattr(
            "mne_nodes.gui.function_widgets.request_package_metadata",
            lambda *args: None,
        )

    def contents():
        return {p: p.is_file() and p.read_bytes() for p in tmp_path.iterdir()}

    before = contents()
    saved_paths = []
    importer = FunctionImporter(code=CODE, on_saved=saved_paths.append)
    qtbot.addWidget(importer)
    assert not importer.save()
    assert contents() == before
    assert saved_paths == []
    assert len(errors) == (case == "existing_file")
    importer.func_config.clear()
    importer.close()


@pytest.mark.parametrize("source", ["text", "file"])
def test_saved_plugin_is_loaded_and_reloaded(
    main_window, importer_input, tmp_path, source
):
    main_window.show_node_picker()
    old_model = main_window.node_picker.functions_view.model()
    if source == "file":
        path = tmp_path / "saved_file_plugin.py"
        path.write_text(CODE, encoding="utf-8")
        main_window.import_functions(file_path=path)
    else:
        main_window.import_functions(code="import math\n\n" + CODE)
    (importer,) = _importers(main_window)
    assert importer.save()
    assert main_window.node_picker.functions_view.model() is not old_model
    assert "transform" in main_window.controller.function_meta
    node = main_window.viewer.add_function_node("transform")
    assert node.input(port_name="raw") is not None
    assert node.output(port_name="result") is not None

    # Re-saving reloads the updated code.
    plugin_name = importer.file_path.stem
    old_plugin = main_window.controller.plugins[plugin_name]
    assert old_plugin.transform(2) == 4
    editor = importer.editors["transform"]
    editor.setPlainText(editor.toPlainText().replace("scale=2", "scale=3"))
    importer.reanalyze()
    assert importer.save()
    updated_plugin = main_window.controller.plugins[plugin_name]
    assert updated_plugin is not old_plugin
    assert updated_plugin.transform(2) == 6
    assert "scale=3" in importer.file_path.read_text(encoding="utf-8")
    importer.func_config.clear()
    importer.close()


def test_saved_plugin_load_failure_is_reported(
    main_window, importer_input, tmp_path, monkeypatch, errors
):
    def fail_load(path):
        raise ImportError("Plugin dependency missing")

    monkeypatch.setattr(main_window.controller, "load_plugin_path", fail_load)
    main_window.import_functions(code=CODE)
    (importer,) = _importers(main_window)
    assert not importer.save()
    assert (_package_dir(tmp_path) / "custom_functions_config.json").is_file()
    assert len(errors) == 1
    assert "transform" not in main_window.controller.function_meta
    _discard_importers(main_window)
