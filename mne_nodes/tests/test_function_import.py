"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

from mne_nodes.gui.function_widgets import FunctionImporter


def test_dialog(qtbot, controller, basic_test_function):
    function_import = FunctionImporter(controller, basic_test_function)
    qtbot.addWidget(function_import)
    qtbot.wait(10000000)
