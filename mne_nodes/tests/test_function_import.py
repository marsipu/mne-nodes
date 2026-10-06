"""GUI entry points and persistence for custom function imports."""

import json

import pytest
from qtpy.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
from qtpy.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent
from qtpy.QtWidgets import QApplication, QLineEdit, QMenu

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
    return calls


def _importers(main_window):
    return main_window.findChildren(FunctionImporter)


def _discard_importers(main_window):
    for importer in _importers(main_window):
        # Avoid unsaved-change prompts during fixture cleanup.
        importer.func_config.clear()
        importer.close()


def _set_clipboard_text(qtbot, text):
    def set_and_check():
        QApplication.clipboard().setText(text)
        return QApplication.clipboard().text() == text

    qtbot.waitUntil(set_and_check)


def test_import_menu_opens_empty_dialog(main_window):
    menu = next(
        menu
        for menu in main_window.menuBar().findChildren(QMenu)
        if menu.title() == "&Plugins"
    )
    next(
        action for action in menu.actions() if action.text() == "&Import Functions..."
    ).trigger()
    (importer,) = _importers(main_window)
    assert importer.isVisible()
    assert not importer.allow_exec
    importer.close()


@pytest.mark.parametrize("target", ["window", "canvas"])
@pytest.mark.parametrize("payload", ["text", "files"])
def test_drop_imports_functions(
    main_window, qtbot, tmp_path, importer_input, target, payload
):
    mime = QMimeData()
    if payload == "files":
        paths = [tmp_path / "first.py", tmp_path / "second.PY"]
        for path in paths:
            path.write_text(CODE, encoding="utf-8")
        mime.setUrls([QUrl.fromLocalFile(str(path)) for path in paths])
    else:
        mime.setText(CODE)
    widget = main_window if target == "window" else main_window.viewer.viewport()
    pos = QPoint(20, 20)
    actions = Qt.DropAction.CopyAction
    buttons = Qt.MouseButton.LeftButton
    modifiers = Qt.KeyboardModifier.NoModifier
    enter = QDragEnterEvent(pos, actions, mime, buttons, modifiers)
    QApplication.sendEvent(widget, enter)
    assert enter.isAccepted()
    move = QDragMoveEvent(pos, actions, mime, buttons, modifiers)
    QApplication.sendEvent(widget, move)
    assert move.isAccepted()
    drop = QDropEvent(QPointF(pos), actions, mime, buttons, modifiers)
    QApplication.sendEvent(widget, drop)
    assert drop.isAccepted()
    importers = _importers(main_window)
    assert len(importers) == (2 if payload == "files" else 1)
    for importer in importers:
        assert importer.isVisible()
        assert "transform" in importer.func_config
        assert not importer.allow_exec
    _discard_importers(main_window)


def test_canvas_paste_and_editor_paste(main_window, qtbot, importer_input):
    _set_clipboard_text(qtbot, CODE)
    main_window.viewer.setFocus()
    qtbot.keyClick(
        main_window.viewer, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier
    )
    (importer,) = _importers(main_window)
    assert "transform" in importer.func_config
    _discard_importers(main_window)
    qtbot.waitUntil(lambda: not _importers(main_window))

    editor = QLineEdit(main_window)
    qtbot.addWidget(editor)
    editor.show()
    editor.setFocus()
    _set_clipboard_text(qtbot, "ordinary parameter text")
    qtbot.keyClick(editor, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    assert editor.text() == "ordinary parameter text"
    assert not _importers(main_window)


def test_paste_handler(main_window, qtbot, importer_input):
    _set_clipboard_text(qtbot, CODE)
    main_window.paste_function_code()
    assert "transform" in _importers(main_window)[0].func_config
    _discard_importers(main_window)


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
    script_path = tmp_path / "custom_functions.py"
    config_path = tmp_path / "custom_functions_config.json"
    assert importer.file_path == script_path
    assert script_path.read_text(encoding="utf-8") == code.replace("scale=2", "scale=3")
    assert "transform" in json.loads(config_path.read_text(encoding="utf-8"))
    assert importer_input == ["string", "folder"]
    importer.func_config.clear()
    importer.close()


def test_file_import_uses_python_encoding(qtbot, tmp_path):
    script = tmp_path / "encoded.py"
    script.write_bytes(("# coding: latin-1\n# caf\xe9\n" + CODE).encode("latin-1"))
    importer = FunctionImporter(file_path=script)
    qtbot.addWidget(importer)
    importer.save()
    assert (tmp_path / "encoded_config.json").is_file()
    assert "caf\xe9" in importer.get_code()
    importer.close()


@pytest.mark.parametrize("source", ["text", "file"])
def test_saved_plugin_is_loaded_automatically(
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
    assert "saved and loaded" in main_window.statusBar().currentMessage()
    node = main_window.viewer.add_function_node("transform")
    assert node.input(port_name="raw") is not None
    assert node.output(port_name="result") is not None
    importer.close()


def test_save_and_quit_loads_plugin(main_window, importer_input, monkeypatch):
    monkeypatch.setattr(
        "mne_nodes.gui.function_widgets.ask_user_custom", lambda *args, **kwargs: True
    )
    main_window.import_functions(code=CODE)
    (importer,) = _importers(main_window)
    assert importer.close()
    assert "transform" in main_window.controller.function_meta


def test_saved_plugin_load_failure_is_reported(
    main_window, importer_input, tmp_path, monkeypatch
):
    errors = []
    monkeypatch.setattr(
        "mne_nodes.gui.function_widgets.ErrorDialog.open",
        lambda self: errors.append(self.windowTitle()),
    )

    def fail_load(path):
        raise ImportError("Plugin dependency missing")

    monkeypatch.setattr(main_window.controller, "load_plugin_path", fail_load)
    main_window.import_functions(code=CODE)
    (importer,) = _importers(main_window)
    assert not importer.save()
    assert (tmp_path / "custom_functions_config.json").is_file()
    assert errors == ["The plugin was saved, but could not be loaded."]
    assert "transform" not in main_window.controller.function_meta
    assert "saved and loaded" not in main_window.statusBar().currentMessage()
    _discard_importers(main_window)


def test_invalid_reanalysis_preserves_editor(qtbot, importer_input, monkeypatch):
    from mne_nodes.gui import function_widgets

    errors = []
    monkeypatch.setattr(
        function_widgets.ErrorDialog, "open", lambda self: errors.append(self)
    )
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


def test_new_text_plugin_does_not_overwrite_existing_file(
    qtbot, importer_input, tmp_path, monkeypatch
):
    from mne_nodes.gui import function_widgets

    errors = []
    monkeypatch.setattr(
        function_widgets.ErrorDialog, "open", lambda self: errors.append(self)
    )
    path = tmp_path / "custom_functions.py"
    path.write_text("original content", encoding="utf-8")
    saved_paths = []
    importer = FunctionImporter(code=CODE, on_saved=saved_paths.append)
    qtbot.addWidget(importer)
    assert not importer.save()
    assert len(errors) == 1
    assert path.read_text(encoding="utf-8") == "original content"
    assert saved_paths == []
    importer.func_config.clear()
    importer.close()
