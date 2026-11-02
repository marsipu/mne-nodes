"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

from qtpy.QtGui import QTextCursor

from mne_nodes.gui.code_editor import CodeFileEditor


def test_insert_code(qtbot, test_code, test_script):
    """Editing a file section saves only that section back into the file."""
    code_func1 = "\n".join(test_code.split("\n")[:4])
    code_func2 = "\n".join(test_code.split("\n")[4:])
    editor = CodeFileEditor(file_path=test_script, file_section=(0, 4))
    qtbot.addWidget(editor)
    assert editor.toPlainText() == code_func1
    new_code = "print('Old code replacement!')\n"
    editor.moveCursor(QTextCursor.MoveOperation.End)
    editor.setPlainText(new_code)
    editor.save()
    with open(test_script, encoding="utf-8") as f:
        saved_content = f.read()
    assert saved_content == new_code + code_func2
