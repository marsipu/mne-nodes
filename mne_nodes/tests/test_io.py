"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import json

import numpy as np
import pytest
from qtpy.QtWidgets import QApplication

import mne_nodes
from mne_nodes.pipeline.io import TypedJSONEncoder, type_json_hook
from mne_nodes.pipeline.settings import Settings


def test_json_serialization(parameter_values):
    """Test if JSON serialization works as expected."""
    serialized = json.dumps(parameter_values, indent=4, cls=TypedJSONEncoder)
    deserialized = json.loads(serialized, object_hook=type_json_hook)
    # Check if the deserialized values match the original ones
    for key, value in parameter_values.items():
        assert key in deserialized, f"Key {key} not found in deserialized JSON"
        if isinstance(value, np.ndarray):
            np.testing.assert_allclose(deserialized[key], value)
        else:
            assert deserialized[key] == value, (
                f"Value mismatch for key {key}: {deserialized[key]} != {value}"
            )
        # Check if the type is preserved
        assert isinstance(deserialized[key], type(value)), (
            f"Type mismatch for key {key}"
        )


def test_settings(qtbot, parameter_values):
    """Test if (Q)Settings work as expected.

    qtbot is needed to initialize the QApplication.
    """

    for mode in ["gui", "headless"]:
        mne_nodes.gui_mode = mode == "gui"

        if mode == "gui":
            app = QApplication.instance()
            app.setApplicationName("test_app")
            app.setOrganizationName("test_org")

        qs = Settings()
        for k, v in parameter_values.items():
            if k not in ["int", "float", "string", "bool", "tuple", "path"]:
                continue
            qs.setValue(k, v)
            value = qs.value(k)
            # Check if the value is set correctly
            assert value == v, f"Expected {v} for key {k}, got {value} with {mode}-mode"
            # Check if the type is preserved
            assert isinstance(value, type(parameter_values[k])), (
                f"Type mismatch for key {k} with {mode}-mode"
            )
            # Check if unsupported types raise an error (e.g. for dicts)
            with pytest.raises(TypeError):
                qs.setValue("unsupported_type", Settings)
            # Check, if None is handled correctly
            qs.setValue("none_type", None)
            assert qs.value("none_type") is None, "Expected None for 'none_type' key"
