"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import pytest
from qtpy.QtWidgets import QApplication

import mne_nodes
from mne_nodes.pipeline.settings import QS


def test_settings(qtbot, parameter_values):
    """Test if (Q)Settings work as expected."""

    for mode in ["gui", "headless"]:
        mne_nodes.gui_mode = mode == "gui"

        if mode == "gui":
            app = QApplication.instance()
            app.setApplicationName("test_app")
            app.setOrganizationName("test_org")

        qs = QS()
        for k, v in parameter_values.items():
            if k not in ["int", "float", "string", "bool"]:
                # Only theese types are supported by (Q)Settings
                continue
            qs.setValue(k, v)
            value = qs.value(k)
            # Check if the value is set correctly
            assert value == v, f"Expected {v} for key {k}, got {value} with {mode}-mode"
            # Check if the type is preserved
            assert isinstance(
                value, type(parameter_values[k])
            ), f"Type mismatch for key {k} with {mode}-mode"
            # Check if unsupported types raise an error (e.g. for dicts)
            with pytest.raises(TypeError):
                qs.setValue("unsupported_type", {"key": "value"})
