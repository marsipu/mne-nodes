"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import builtins
import keyword
from os.path import isfile
from pathlib import Path

import darkdetect
from qtpy.QtCore import QRegularExpression, Signal
from qtpy.QtGui import (
    QColor,
    QFont,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
    QTextFormat,
)
from qtpy.QtWidgets import QPlainTextEdit, QPushButton, QTextEdit, QVBoxLayout, QWidget

from mne_nodes.gui.gui_utils import get_user_input
from mne_nodes.logger import logger
from mne_nodes.pipeline.pipeline_utils import change_file_section
from mne_nodes.pipeline.settings import Settings

# Color palettes for the syntax highlighter, inspired by common editor themes.
HIGHLIGHT_COLORS = {
    "light": {
        "keyword": "#0000ff",
        "builtin": "#267f99",
        "self": "#7f0055",
        "decorator": "#af00db",
        "definition": "#795e26",
        "number": "#098658",
        "string": "#a31515",
        "comment": "#008000",
        "current_line": "#e8f2ff",
        "error_line": "#ffd6d6",
    },
    "dark": {
        "keyword": "#569cd6",
        "builtin": "#4ec9b0",
        "self": "#c586c0",
        "decorator": "#dcdcaa",
        "definition": "#dcdcaa",
        "number": "#b5cea8",
        "string": "#ce9178",
        "comment": "#6a9955",
        "current_line": "#2a2d3a",
        "error_line": "#5a2a2a",
    },
}


def resolve_theme(theme=None):
    """Resolve *theme* (``"light"``/``"dark"``/``"auto"``/``None``) to an actual theme."""
    if theme is None:
        theme = Settings().get("app_theme")
    if theme not in ("light", "dark"):
        try:
            detected = darkdetect.theme()
        except Exception:  # noqa: BLE001 - fall back to light theme on any failure
            detected = None
        theme = (detected or "light").lower()
        if theme not in ("light", "dark"):
            theme = "light"
    return theme


class PythonHighlighter(QSyntaxHighlighter):
    """Python syntax highlighter with a light and a dark color scheme."""

    _STATE_NONE = -1
    _STATE_TRIPLE_SINGLE = 1
    _STATE_TRIPLE_DOUBLE = 2

    _TRIPLE_SINGLE_RE = QRegularExpression(r"'''")
    _TRIPLE_DOUBLE_RE = QRegularExpression(r'"""')

    def __init__(self, parent=None, theme=None):
        super().__init__(parent)
        self.colors = HIGHLIGHT_COLORS[resolve_theme(theme)]
        self._rules = []
        self._string_format = None
        self._build_rules()

    def set_theme(self, theme):
        """Switch the highlighter to *theme* (``"light"`` or ``"dark"``) and rehighlight."""
        self.colors = HIGHLIGHT_COLORS[resolve_theme(theme)]
        self._build_rules()
        self.rehighlight()

    def _format(self, color_key, bold=False, italic=False):
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(self.colors[color_key]))
        if bold:
            fmt.setFontWeight(QFont.Weight.Bold)
        if italic:
            fmt.setFontItalic(True)
        return fmt

    def _build_rules(self):
        self._rules = []

        keyword_fmt = self._format("keyword", bold=True)
        for word in [*keyword.kwlist, "match", "case"]:
            self._rules.append((QRegularExpression(rf"\b{word}\b"), keyword_fmt, 0))

        builtin_fmt = self._format("builtin")
        builtin_names = sorted(
            name for name in dir(builtins) if not name.startswith("_")
        )
        for name in builtin_names:
            self._rules.append((QRegularExpression(rf"\b{name}\b"), builtin_fmt, 0))

        self_fmt = self._format("self", italic=True)
        self._rules.append((QRegularExpression(r"\b(self|cls)\b"), self_fmt, 0))

        decorator_fmt = self._format("decorator")
        self._rules.append((QRegularExpression(r"@\w+(\.\w+)*"), decorator_fmt, 0))

        definition_fmt = self._format("definition", bold=True)
        self._rules.append((QRegularExpression(r"\bdef\s+(\w+)"), definition_fmt, 1))
        self._rules.append((QRegularExpression(r"\bclass\s+(\w+)"), definition_fmt, 1))

        number_fmt = self._format("number")
        self._rules.append(
            (
                QRegularExpression(
                    r"\b0[xX][0-9A-Fa-f_]+\b|\b0[bB][01_]+\b|\b0[oO][0-7_]+\b|"
                    r"\b\d[\d_]*(\.\d[\d_]*)?([eE][+-]?\d+)?[jJ]?\b"
                ),
                number_fmt,
                0,
            )
        )

        string_fmt = self._format("string")
        self._string_format = string_fmt
        self._rules.append(
            (
                QRegularExpression(
                    r'(?i)[rbfu]{0,2}"(?:\\.|[^"\\])*"|[rbfu]{0,2}\'(?:\\.|[^\'\\])*\''
                ),
                string_fmt,
                0,
            )
        )

        # Comments last so they overwrite anything matched inside them.
        comment_fmt = self._format("comment", italic=True)
        self._rules.append((QRegularExpression(r"#[^\n]*"), comment_fmt, 0))

    def highlightBlock(self, text):
        for pattern, fmt, group in self._rules:
            it = pattern.globalMatch(text)
            while it.hasNext():
                match = it.next()
                start = match.capturedStart(group)
                length = match.capturedLength(group)
                if start >= 0 and length > 0:
                    self.setFormat(start, length, fmt)

        self.setCurrentBlockState(self._STATE_NONE)
        in_multiline = self._match_multiline(
            text, self._TRIPLE_DOUBLE_RE, self._STATE_TRIPLE_DOUBLE
        )
        if not in_multiline:
            self._match_multiline(
                text, self._TRIPLE_SINGLE_RE, self._STATE_TRIPLE_SINGLE
            )

    def _match_multiline(self, text, delimiter, state):
        if self.previousBlockState() == state:
            start = 0
            skip = 0
        else:
            match = delimiter.match(text)
            start = match.capturedStart()
            skip = match.capturedLength()

        while start >= 0:
            match = delimiter.match(text, start + skip)
            end = match.capturedStart()
            if end == -1:
                self.setCurrentBlockState(state)
                length = len(text) - start
            else:
                length = end - start + match.capturedLength()
            self.setFormat(start, length, self._string_format)
            next_match = delimiter.match(text, start + length)
            start = next_match.capturedStart()
            skip = next_match.capturedLength()

        return self.currentBlockState() == state


class CodeEditor(QPlainTextEdit):
    """A ``QPlainTextEdit`` with Python syntax highlighting and problem markers.

    Parameters
    ----------
    parent : QWidget | None
        The parent widget.
    theme : str | None
        ``"light"``, ``"dark"`` or ``None``/``"auto"`` to follow the application theme.
    """

    editingFinished = Signal()

    def __init__(self, parent=None, theme=None):
        super().__init__(parent)
        self.setFont(QFont("Consolas", 12))
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))
        self.highlighter = PythonHighlighter(self.document(), theme=theme)
        self._problem_line = None
        self._focus_text = None
        self.cursorPositionChanged.connect(self._update_extra_selections)
        self._update_extra_selections()

    def set_theme(self, theme):
        """Switch the syntax highlighting to *theme* (``"light"`` or ``"dark"``)."""
        self.highlighter.set_theme(theme)
        self._update_extra_selections()

    def set_problem(self, lineno, message=""):
        """Mark *lineno* (1-indexed) as containing a problem, with *message* as tooltip."""
        self._problem_line = lineno
        self.setToolTip(message)
        self._update_extra_selections()

    def clear_problem(self):
        """Clear any problem marker set via :meth:`set_problem`."""
        self.set_problem(None)

    def _update_extra_selections(self):
        selections = []
        colors = self.highlighter.colors

        current_selection = QTextEdit.ExtraSelection()
        current_selection.format.setBackground(QColor(colors["current_line"]))
        current_selection.format.setProperty(
            QTextFormat.Property.FullWidthSelection, True
        )
        current_selection.cursor = self.textCursor()
        current_selection.cursor.clearSelection()
        selections.append(current_selection)

        if self._problem_line is not None:
            problem_selection = QTextEdit.ExtraSelection()
            problem_selection.format.setBackground(QColor(colors["error_line"]))
            problem_selection.format.setProperty(
                QTextFormat.Property.FullWidthSelection, True
            )
            block = self.document().findBlockByNumber(self._problem_line - 1)
            cursor = QTextCursor(block)
            problem_selection.cursor = cursor
            selections.append(problem_selection)

        self.setExtraSelections(selections)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self._focus_text = self.toPlainText()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        if self.toPlainText() != self._focus_text:
            self.editingFinished.emit()


class CodeFileEditor(CodeEditor):
    """An editor for Python code.

    Parameters
    ----------
    file_path : Path
        The path to a file with code.
    parent : QWidget or None
        The parent widget.
    file_section : tuple[int, int] or None
        The section of a code by first and (excluded) last line number, 0-indexed.
    read_only : bool
        Set to True to make the code read-only.
    """

    codeSaved = Signal(Path)

    def __init__(
        self, file_path, parent=None, file_section=None, read_only=False, theme=None
    ):
        super().__init__(parent, theme=theme)
        self.file_section = file_section
        self.file_path = self._file_path = file_path
        self.setReadOnly(read_only)

    @property
    def file_path(self):
        return self._file_path

    @file_path.setter
    def file_path(self, value):
        if isfile(value):
            with open(value, encoding="utf-8") as f:
                code = f.read()
            if self.file_section is not None:
                start, end = self.file_section
                code_lines = code.splitlines()
                code = "\n".join(code_lines[start:end])
            self.setPlainText(code)
        self._file_path = value
        if value:
            self.setWindowTitle(f"Editing: {Path(value).name}")
        else:
            self.setWindowTitle("New Python File")

    def save(self):
        if self.file_path is None:
            folder_path = get_user_input(
                "Select the folder where the file should be saved", "folder"
            )
            file_name = get_user_input("Enter the file name (without '.py')", "string")
            self.file_path = Path(folder_path) / f"{file_name}.py"
        code = self.toPlainText()
        # Insert code into a specific section of a file if defined
        if self.file_section is not None:
            change_file_section(self.file_path, self.file_section, code)
        self.codeSaved.emit(self.file_path)
        logger.info(f"Saved code to file: {self.file_path}")


class CodeEditorWidget(QWidget):
    def __init__(self, parent=None, **kwargs):
        super().__init__(parent)
        self.editor = CodeFileEditor(**kwargs)
        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self.editor.save)
        layout = QVBoxLayout()
        layout.addWidget(self.editor)
        layout.addWidget(self.save_button)
        self.setLayout(layout)
