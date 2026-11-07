"""Test-mode isolation and explicit GUI routing opt-in."""

from unittest.mock import Mock

import pytest

import mne_nodes
from mne_nodes.backend.io import load_json
from mne_nodes.gui.dialogs import user_interaction


@pytest.mark.parametrize(
    "expected", [False, pytest.param(True, marks=pytest.mark.gui_mode)]
)
def test_marker_controls_json_and_notification_routing(expected, tmp_path, monkeypatch):
    """The marker applies before setup and both consumers use the current mode."""
    assert mne_nodes.gui_mode is expected
    path = tmp_path / "data.json"
    path.write_text('{"value": 1}', encoding="utf-8")
    dialog = Mock(return_value={"value": 1})
    warning = Mock()
    monkeypatch.setattr("mne_nodes.backend.io.json_load_dialog", dialog)
    monkeypatch.setattr(user_interaction, "warning_message", warning)
    assert load_json(path) == {"value": 1}
    user_interaction.raise_user_attention("Mode routing check")
    assert dialog.call_count == int(expected)
    assert warning.call_count == int(expected)
    load_json(path, no_gui=True)
    assert dialog.call_count == int(expected)
