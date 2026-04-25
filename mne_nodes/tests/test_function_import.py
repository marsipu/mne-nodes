"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import pprint

from mne_nodes.gui.function_widgets import FunctionImporter


# ToDo: Proper tests
def test_dialog(qtbot, basic_functions):
    function_import = FunctionImporter(basic_functions)
    qtbot.addWidget(function_import)

    # Increase to check functionality
    qtbot.wait(100000)
    function_import.close()
    pprint.pprint(function_import.func_config)
