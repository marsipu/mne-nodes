# -*- coding: utf-8 -*-
import logging
from os.path import isfile
from pathlib import Path

from qtpy.QtCore import QRegularExpression
from qtpy.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont
from qtpy.QtWidgets import QPlainTextEdit, QWidget, QVBoxLayout, QPushButton

from mne_nodes.gui.gui_utils import get_user_input


class PythonHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._highlighting_rules = []
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("#0077aa"))
        keyword_format.setFontWeight(QFont.Bold)
        keywords = [
            "and",
            "as",
            "assert",
            "break",
            "class",
            "continue",
            "def",
            "del",
            "elif",
            "else",
            "except",
            "False",
            "finally",
            "for",
            "from",
            "global",
            "if",
            "import",
            "in",
            "is",
            "lambda",
            "None",
            "nonlocal",
            "not",
            "or",
            "pass",
            "raise",
            "return",
            "True",
            "try",
            "while",
            "with",
            "yield",
        ]
        for word in keywords:
            pattern = QRegularExpression(r"\b" + word + r"\b")
            self._highlighting_rules.append((pattern, keyword_format))

        # String format
        string_format = QTextCharFormat()
        string_format.setForeground(QColor("#aa5500"))
        self._highlighting_rules.append((QRegularExpression(r"'.*?'"), string_format))
        self._highlighting_rules.append((QRegularExpression(r"'.*?'"), string_format))

        # Comment format
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#888888"))
        comment_format.setFontItalic(True)
        self._highlighting_rules.append((QRegularExpression(r"#.*"), comment_format))

    def highlightBlock(self, text):
        for pattern, fmt in self._highlighting_rules:
            it = pattern.globalMatch(text)
            while it.hasNext():
                match = it.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), fmt)


class CodeEditor(QPlainTextEdit):
    def __init__(self, parent=None, file_path=None, file_section=None, read_only=False):
        super().__init__(parent)
        self.setFont(QFont("Consolas", 12))
        self.highlighter = PythonHighlighter(self.document())
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.file_path = self._file_path = file_path
        self.file_section = file_section
        self.setReadOnly(read_only)

    @property
    def file_path(self):
        return self._file_path

    @file_path.setter
    def file_path(self, value):
        if isfile(value):
            with open(value, "r", encoding="utf-8") as f:
                code = f.read()
            if self.file_section is not None:
                start, end = self.file_section
                code_lines = code.split("\n")
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
            start, end = self.file_section
            with open(self.file_path, "r") as f:
                existing_code = f.read()
            code_split = existing_code.split("\n")
            new_split = code.split("\n")
            code_split[start:end] = new_split
            code = "\n".join(code_split)
        with open(self.file_path, "w", encoding="utf-8") as f:
            f.write(code)
        logging.info(f"Saved code to file: {self.file_path}")


class CodeEditorWidget(QWidget):
    def __init__(self, parent=None, **kwargs):
        super().__init__(parent)
        self.editor = CodeEditor(**kwargs)
        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self.editor.save)
        layout = QVBoxLayout()
        layout.addWidget(self.editor)
        layout.addWidget(self.save_button)
        self.setLayout(layout)
