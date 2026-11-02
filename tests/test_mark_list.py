"""Tests for dictionary-driven list markings."""

from types import SimpleNamespace

import pytest

from mne_nodes.gui.loading_widgets import EventIDGui, EvIDApply
from mne_nodes.gui.widgets import AssignWidget, MarkList


def test_mark_list_external_changes_and_replacement(qtbot):
    """External mutations and empty replacements retain dictionary semantics."""
    data = {"first": True}
    widget = MarkList(data)
    qtbot.addWidget(widget)
    data["first"] = False
    data["second"] = True
    with qtbot.waitSignal(widget.model.layoutChanged):
        widget.content_changed()
    assert widget.model.rowCount() == 2
    assert widget.model.data(widget.model.index(1, 0)) == "second"
    del data["first"]
    widget.content_changed()
    assert widget.model.getData(widget.model.index(0, 0)) == "second"

    replacement = {"new": True}
    widget.replace_data(replacement)
    assert widget.model._data is replacement
    assert widget.model.data(widget.model.index(0, 0)) == "new"
    empty = {}
    widget.replace_data(empty)
    assert widget.model._data is empty
    assert widget.model.rowCount() == 0
    assert widget.model.getData(widget.model.createIndex(0, 0)) is None
    empty["added"] = True
    widget.content_changed()
    assert widget.model.data(widget.model.index(0, 0)) == "added"


@pytest.mark.parametrize("data", [["item"], {"item": []}, {"item": 1}, {"item": None}])
def test_mark_list_invalid_data(qtbot, data):
    """Invalid input raises explicitly and cannot replace valid data."""
    with pytest.raises(TypeError):
        MarkList(data)
    original = {"item": True}
    widget = MarkList(original)
    qtbot.addWidget(widget)
    with pytest.raises(TypeError):
        widget.replace_data(data)
    assert widget.model._data is original
    original["item"] = []
    with pytest.raises(TypeError):
        widget.content_changed()


def test_assignments_update_data_and_marks(qtbot):
    """Assignments and event IDs are stored and refresh the file marks."""
    assignments = {"one": ""}
    widget = AssignWidget(["one", "two"], ["property"], assignments)
    qtbot.addWidget(widget)
    assert widget.items_w.model._data == {"one": True, "two": False}
    widget.items_w.select(["two"])
    widget.props_w.view.setCurrentIndex(widget.props_w.model.index(0, 0))
    widget.assign()
    assert assignments == {"one": "", "two": "property"}
    assert widget.items_w.model._data == {"one": True, "two": True}

    marks = MarkList({"one": False, "two": False})
    qtbot.addWidget(marks)
    project = SimpleNamespace(
        all_meeg=["one", "two"], meeg_event_id={}, sel_event_id={}
    )
    state = SimpleNamespace(
        pr=project,
        name="one",
        event_id={"stimulus": 1},
        checked_labels=["stimulus"],
        queries={},
        files=marks,
    )
    EventIDGui.save_event_id(state)
    assert marks.model._data == {"one": True, "two": False}
    EvIDApply.apply_evid(SimpleNamespace(p=state, apply_to=["two"]))
    assert marks.model._data == {"one": True, "two": True}
    assert project.meeg_event_id["two"] == state.event_id
    assert project.meeg_event_id["two"] is not state.event_id
