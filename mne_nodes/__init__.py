"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import sys

# Global variables to check the platform
ismac = sys.platform.startswith("darwin")
iswin = sys.platform.startswith("win32")
islin = not ismac and not iswin

# Variable to store gui/headless mode, should not be imported directly
# but accessed via mne_nodes.gui_mode
gui_mode = True

# Keep reference to Qt-objects without parent for tests
# and to avoid garbage collection
_object_refs = {
    "welcome_window": None,
    "main_window": None,
    "plot_manager": None,
    "dialogs": {},
    "parameter_widgets": {},
    "color_tester": None,
}
