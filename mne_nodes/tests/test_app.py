# -*- coding: utf-8 -*-
"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""


def test_headless_run():
    import sys
    from mne_nodes.__main__ import main
    from mne_nodes.pipeline import pipeline_utils

    # Simulate command line arguments for headless run
    sys.argv = ["mne-nodes", "--headless"]

    # Run the main function
    main()

    # Check if the application is running in headless mode
    assert pipeline_utils.gui_mode is False


def test_legacy_import_check(monkeypatch):
    from mne_nodes.pipeline.legacy import legacy_import_check, uninstall_package

    # Monkeypatch input
    monkeypatch.setattr("builtins.input", lambda x: "y")

    # Test legacy import check
    legacy_import_check("pip-install-test")
    __import__("pip_install_test")
    uninstall_package("pip-install-test")
