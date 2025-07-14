# -*- coding: utf-8 -*-
"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""
from os.path import join

from PySide6.QtWidgets import QMessageBox

from mne_nodes.pipeline.controller import Controller


# ToDo Next: Make this test run
def test_init(qtbot, monkeypatch, tmpdir):

    monkeypatch.setattr("qtpy.QtWidgets.QMessageBox.question", lambda x, y, z: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr("qtpy.QtWidgets.QInputDialog.getText", lambda x, y, z: ("test", True))
    monkeypatch.setattr("qtpy.QtWidgets.QFileDialog.getExistingDirectory", lambda x, y: tmpdir)

    # Initialize the controller in gui mode
    ct = Controller()

    # Initialize another controller with the new config-file
    ct2 = Controller(config_path=join(tmpdir, "test_config.json"))

    # ToDo: Initialize the controller in headless mode
