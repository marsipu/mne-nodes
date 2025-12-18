"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import pprint

from mne_nodes.gui.function_widgets import FunctionImporter


def test_dialog(qtbot, controller, basic_functions):
    function_import = FunctionImporter(controller, basic_functions)
    qtbot.addWidget(function_import)

    # Increase to check functionality
    qtbot.wait(1000000)
    function_import.close()
    pprint.pprint(function_import.func_config)


def test_reanalyze(qtbot, controller, basic_functions, basic_functions_alt):
    function_import = FunctionImporter(controller, basic_functions)
    qtbot.addWidget(function_import)

    # Increase to check functionality
    qtbot.wait(1000000)
    function_import.close()
    pprint.pprint(function_import.func_config)
