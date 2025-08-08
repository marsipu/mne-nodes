"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import sys


import mne_nodes
from mne_nodes.gui.main_window import MainWindow
from mne_nodes.pipeline.controller import Controller


def test_headless_run():
    from mne_nodes.__main__ import main

    # Simulate command line arguments for headless run
    sys.argv = ["mne-nodes", "--headless"]

    # Run the main function
    main()

    # Check if the application is running in headless mode
    assert mne_nodes.gui_mode is False


def test_legacy_import_check(monkeypatch):
    from mne_nodes.pipeline.legacy import legacy_import_check, uninstall_package

    # Monkeypatch input
    monkeypatch.setattr("builtins.input", lambda x: "y")

    # Test legacy import check
    legacy_import_check("pip-install-test")
    __import__("pip_install_test")
    uninstall_package("pip-install-test")


def test_app_start(controller, main_window):
    """Test the application startup process with a controller and main
    window."""
    # Ensure the controller is initialized correctly
    assert isinstance(controller, Controller)
    assert controller.name == "test"

    # Ensure the main window is created and visible
    assert isinstance(main_window, MainWindow)
    assert main_window.isVisible()

    # Verify the controller is set in the main window
    assert main_window.controller == controller

    # Clean up by closing the main window
    main_window.close()
