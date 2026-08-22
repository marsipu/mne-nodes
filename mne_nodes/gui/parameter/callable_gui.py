"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

from __future__ import annotations

import ast
from typing import Any

from qtpy.QtCore import Qt
from qtpy.QtWidgets import QLabel, QVBoxLayout

from mne_nodes.gui.code_editor import CodeEditor
from mne_nodes.pipeline.controller import Controller
from mne_nodes.pipeline.settings import Settings

from .param import Param


def check_function_code(code: str) -> tuple[str | None, int | None]:
    """Statically check *code* for exactly one top-level function/class definition.

    This does not execute *code*, it only parses it. Returns a tuple of
    ``(error_message, lineno)``, both ``None`` if *code* looks valid.
    """
    if not code or not code.strip():
        return "No code entered.", None
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return f"Syntax error: {exc.msg} (line {exc.lineno})", exc.lineno
    definitions = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    if not definitions:
        return "No top-level function or class definition found.", None
    if len(definitions) > 1:
        extra = definitions[1]
        return (
            f"Only one function/class definition is allowed, found another '{extra.name}' (line {extra.lineno}).",
            extra.lineno,
        )
    return None, None


def evaluate_function_code(code: str) -> tuple[Any | None, str | None]:
    """Execute *code* and return ``(callable_or_None, error_message_or_None)``.

    *code* must define exactly one top-level function or class, which becomes
    the resulting callable.

    .. warning::
        This executes *code* with the full Python interpreter. Never call this
        with untrusted input.
    """
    error, _ = check_function_code(code)
    if error:
        return None, error

    tree = ast.parse(code)
    definition_name = next(
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    )
    namespace = {}
    try:
        exec(compile(tree, "<parameter_code>", "exec"), namespace)  # noqa: S102
    except Exception as exc:  # noqa: BLE001 - user code can raise anything
        return None, f"Error while executing code: {exc}"

    func = namespace[definition_name]
    if not callable(func):
        return None, f"'{definition_name}' is not callable."
    return func, None


class CallableGui(Param):
    """Parameter GUI for defining a callable via a code editor.

    The user types Python code that defines exactly one top-level function (or
    class), which becomes the parameter's :attr:`value`. The source code (not
    the callable) is what gets persisted, and is re-evaluated when loaded.

    .. warning::
        Everything entered here is executed with the full Python interpreter
        when the value is committed. Never paste or run code you do not trust.
    """

    data_type = object

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)

        self.warning_label = QLabel(
            "\u26a0 Executed as Python \u2013 don't paste untrusted code!"
        )
        self.warning_label.setWordWrap(False)
        self.warning_label.setToolTip(
            "Code entered here is executed as Python when the value is applied. "
            "Never paste or run code you do not trust."
        )
        self.warning_label.setStyleSheet(
            "background-color: #f5c518; color: #000000; padding: 2px 4px; "
            "border-radius: 3px;"
        )

        self.editor = CodeEditor()
        self.editor.setMinimumHeight(150)
        self.editor.setToolTip(
            "Define exactly one function (or class) here; it becomes the "
            "parameter value."
        )
        self.editor.textChanged.connect(self._check_code)
        self.editor.editingFinished.connect(self._on_widget_changed)

        self.problem_label = QLabel()
        self.problem_label.setWordWrap(True)
        self.problem_label.setStyleSheet("color: #b00000;")
        self.problem_label.hide()

        code_layout = QVBoxLayout()
        code_layout.addWidget(self.warning_label)
        code_layout.addWidget(self.editor)
        code_layout.addWidget(self.problem_label)
        self.init_ui(code_layout)

        self.editor.setPlainText(self._code)
        self._check_code()

    def _check_code(self):
        code = self.editor.toPlainText()
        error, lineno = check_function_code(code)
        if error:
            self.editor.set_problem(lineno or 1, error)
            self.problem_label.setText(f"\u26a0 {error}")
            self.problem_label.show()
        else:
            self.editor.clear_problem()
            self.problem_label.hide()

    def _set_widget_value(self, value):
        if self.editor.toPlainText() != self._code:
            self.editor.setPlainText(self._code)

    def _on_widget_changed(self):
        # Bypass the value setter here so a failed evaluation keeps self._error
        # set (the setter's None-branch would otherwise clear it as if the
        # user had explicitly disabled the parameter). Also don't treat the
        # none-checkbox/groupbox as "disabled" while it's only mirroring a
        # failed evaluation, so users can keep fixing the code.
        if self.none_select and not self._is_enabled() and self._error is None:
            self.value = None
            return
        widget_value = self._get_widget_value()
        if widget_value != self._value:
            self._value = widget_value
            if self._value is not None:
                self._previous_value = self._value
            self._update_param()

    def _on_none_changed(self, checked=None):
        disabling = not (checked == Qt.CheckState.Checked or checked is True)
        if disabling and self._value is None:
            # None-checkbox/groupbox is only mirroring a value that is already
            # None because evaluation failed; don't clear self._error here.
            return
        super()._on_none_changed(checked)

    def _update_gui(self):
        super()._update_gui()
        # Keep the editor usable so users can fix code right after a failed
        # evaluation, even though None-select normally disables the whole widget.
        if self._error:
            self.editor.setEnabled(True)

    def _get_widget_value(self):
        code = self.editor.toPlainText()
        self._code = code
        func, self._error = evaluate_function_code(code)
        return func

    @property
    def value(self):
        return super().value

    @value.setter
    def value(self, new_value):
        if new_value is None:
            self._value = None
            self._error = None
        elif isinstance(new_value, str):
            self._code = new_value
            self._value, self._error = evaluate_function_code(new_value)
        elif callable(new_value):
            self._value = new_value
            self._error = None
        else:
            raise TypeError(
                f"Value for {self.name} must be code (str), a callable or None, "
                f"but got type {type(new_value)}."
            )
        if self._value is not None:
            self._previous_value = self._value
        self._update_param()

    def _load_from_data(self, name):
        if isinstance(self.data, Controller):
            code = self.data.parameter(name, function_name=self.function_name)
        elif isinstance(self.data, dict):
            code = self.data.get(name, self.default)
        elif isinstance(self.data, Settings) and name in self.data:
            code = self.data.get(name)
        else:
            code = self.default
        if not isinstance(code, str):
            code = self.default if isinstance(self.default, str) else ""
        self._code = code
        func, self._error = evaluate_function_code(code)
        return func

    def _save_to_data(self, name, value):
        super()._save_to_data(name, self._code if value is not None else None)
