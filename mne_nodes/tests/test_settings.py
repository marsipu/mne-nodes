# -*- coding: utf-8 -*-
"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""
from qtpy.QtWidgets import QApplication
from qtpy.QtCore import QSettings

from mne_nodes.pipeline import pipeline_utils
from mne_nodes.pipeline.pipeline_utils import QS


def test_settings(qtbot, parameter_values):
    """Test if (Q)Settings work as expected."""

    for mode in ["gui", "headless"]:
        pipeline_utils.gui_mode = mode == "gui"

        if mode == "gui":
            app = QApplication.instance()
            app.setApplicationName("test_app")
            app.setOrganizationName("test_org")

        qs = QS()
        for k, v in parameter_values.items():
            if k in ["tupl", "list", "check_list", "dict", "color", "combo", "slider", "path"]:
                # These types are not supported by QSettings
                continue
            qs.setValue(k, v)
            value = qs.value(k)
            # Check if the value is set correctly
            assert value == v, \
                f"Expected {v} for key {k}, got {value} with {mode}-mode"
            # Check if the type is preserved
            assert isinstance(value, type(parameter_values[k])), \
                f"Type mismatch for key {k} with {mode}-mode"
