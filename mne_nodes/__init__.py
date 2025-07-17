"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

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
