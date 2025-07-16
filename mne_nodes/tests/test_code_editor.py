# -*- coding: utf-8 -*-
"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""
from qtpy.QtGui import QTextCursor

from mne_nodes.gui.code_editor import CodeEditorWidget, CodeEditor


def test_load_save(qtbot, tmp_path, test_script):
    # Create the editor widget and load the file
    widget = CodeEditorWidget(file_path=test_script)
    qtbot.addWidget(widget)
    widget.show()
    # Simulate editing
    original_code = widget.editor.toPlainText()
    new_code = "print('Hello, World!')\n"
    widget.editor.moveCursor(QTextCursor.MoveOperation.End)
    widget.editor.insertPlainText(new_code)
    # Save changes
    widget.editor.save()
    # Verify file contents
    with open(test_script, "r", encoding="utf-8") as f:
        saved_content = f.read()
    assert saved_content == original_code + new_code


def test_insert_code(qtbot, tmp_path, test_code, test_script):
    # Test insertion of code into a specific section
    # Todo Next: Finish this test and then FINISH Function Node!
    code_func1 = "\n".join(test_code.split("\n")[:4])
    print(code_func1)
    editor = CodeEditor(file_path=test_script, file_section=(0, 4))
    qtbot.addWidget(editor)
    # Assert only section code is shown
