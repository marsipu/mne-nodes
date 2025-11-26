"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import json
from datetime import datetime

import numpy as np
import pytest

from mne_nodes.pipeline.io import TypedJSONEncoder, type_json_hook
from mne_nodes.pipeline.settings import Settings


def test_json_serialization(parameter_values):
    """Test if JSON serialization works as expected."""
    # Add nested dict with possible extra types
    # ToDo: Add ParameterGuis for array (nested TableView) and datetime
    parameter_values.update(
        {
            "array": np.array([[1, 2, 3], [4, 5, 6]]),
            "datetime": datetime(2000, 1, 1, 12, 0, 0),
        }
    )
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


def test_settings(parameter_values):
    """Test if (Q)Settings work as expected.

    qtbot is needed to initialize the QApplication.
    """
    settings = Settings()
    for k, v in parameter_values.items():
        if k not in ["int", "float", "string", "bool", "tuple", "path"]:
            continue
        settings.set(k, v)
        value = settings.get(k)
        # Check if the value is set correctly
        assert value == v, f"Expected {v} for key {k}, got {value}"
        # Check if the type is preserved
        assert isinstance(value, type(parameter_values[k])), (
            f"Type mismatch for key {k}"
        )
        # Check if unsupported types raise an error (e.g. for dicts)
        with pytest.raises(TypeError):
            settings.set("unsupported_type", Settings)
        # Check, if None is handled correctly
        settings.set("none_type", None)
        assert settings.get("none_type") is None, "Expected None for 'none_type' key"
