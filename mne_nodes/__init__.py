"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import logging
import os
import sys


# Global variables to check the platform
ismac = sys.platform.startswith("darwin")
iswin = sys.platform.startswith("win32")
islin = not ismac and not iswin

# Variable to store gui/headless mode, should not be imported directly
# but accessed via mne_nodes.gui_mode
gui_mode = True


# Check if running in debug mode
def debug_mode():
    return os.environ.get("MNENODES_DEBUG", False) == "true"


def main_widget():
    from qtpy.QtWidgets import QApplication

    if _widgets["main_window"] is not None:
        return _widgets["main_window"]
    else:
        logging.warning("MainWindow hasn't been initialized yet!")
        active_window = QApplication.activeWindow()
        if active_window is not None:
            return active_window
        else:
            logging.warning("There is no active window!")
            return None


# Keep reference to Qt-objects without parent for tests
# and to avoid garbage collection
_widgets = {
    "main_window": None,
    "viewer": None,
    "plot_manager": None,
    "dialogs": {},
    "parameter_widgets": {},
    "color_tester": None,
}
