"""Tests for dictionary-driven list markings."""

from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import Mock

import pytest
from qtpy.QtCore import QModelIndex, Qt
from qtpy.QtGui import QColor, QIcon, QPixmap
from qtpy.QtWidgets import QApplication, QStyle

from mne_nodes.gui.widgets import AssignWidget, MarkList


def test_mark_list_icons(qtbot):
    """String and boolean marks resolve to standard or custom icons."""
    pixmap = QPixmap(16, 16)
    pixmap.fill(QColor("red"))
    custom_icon = QIcon(pixmap)
    data = {"ready": "done", "waiting": "pending", "yes": True, "no": False}
    widget = MarkList(
        data,
        mark_icons={
            "done": custom_icon,
            "pending": "SP_BrowserReload",
            True: "SP_DialogApplyButton",
            False: "SP_DialogCancelButton",
        },
    )
    qtbot.addWidget(widget)

    assert widget.model._data is data
    assert widget.model.rowCount() == 4
    assert widget.model.rowCount(widget.model.index(0, 0)) == 0
    for row, item in enumerate(data):
        index = widget.model.index(row, 0)
        assert widget.model.getData(index) == item
        assert widget.model.data(index, Qt.ItemDataRole.DisplayRole) == item
        assert not widget.model.data(index, Qt.ItemDataRole.DecorationRole).isNull()

    assert (
        widget.model.data(widget.model.index(0, 0), Qt.ItemDataRole.DecorationRole)
        is custom_icon
    )
    actual = widget.model.data(widget.model.index(1, 0), Qt.ItemDataRole.DecorationRole)
    expected = QApplication.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload)
    assert actual.pixmap(16, 16).toImage() == expected.pixmap(16, 16).toImage()


def test_mark_list_defaults_and_selection(qtbot):
    """Default boolean icons do not turn marks into checkboxes."""
    widget = MarkList(
        {"one": True, 2: False, "unmapped": "pending"},
        extended_selection=True,
        show_index=True,
    )
    qtbot.addWidget(widget)
    widget.select(["one", 2])
    assert widget.get_selected() == ["one", 2]
    index = widget.model.index(1, 0)
    widget.view.setCurrentIndex(index)
    assert widget.get_current() == 2
    assert widget.model.data(index, Qt.ItemDataRole.DisplayRole) == "1: 2"
    assert widget.model.data(index, Qt.ItemDataRole.EditRole) == "2"
    assert widget.model.data(index, Qt.ItemDataRole.CheckStateRole) is None
    assert not widget.model.flags(index) & Qt.ItemFlag.ItemIsUserCheckable
    assert not widget.model.flags(index) & Qt.ItemFlag.ItemIsEditable
    for row, name in enumerate(["SP_DialogApplyButton", "SP_DialogCancelButton"]):
        actual = widget.model.data(
            widget.model.index(row, 0), Qt.ItemDataRole.DecorationRole
        )
        expected = QApplication.style().standardIcon(
            getattr(QStyle.StandardPixmap, name)
        )
        assert actual.pixmap(16, 16).toImage() == expected.pixmap(16, 16).toImage()
    assert (
        widget.model.data(widget.model.index(2, 0), Qt.ItemDataRole.DecorationRole)
        is None
    )
    assert widget.model.getData(QModelIndex()) is None
    assert widget.model.data(QModelIndex(), Qt.ItemDataRole.DecorationRole) is None


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


def test_mark_list_class_config_and_empty_config(qtbot):
    """Subclasses can configure icons; explicit empty mappings disable them."""

    class StatusList(MarkList):
        mark_icons: ClassVar = {"ready": "SP_DialogApplyButton"}

    configured = StatusList({"item": "ready"})
    disabled = StatusList({"item": "ready"}, mark_icons={})
    empty = MarkList()
    another_empty = MarkList()
    for widget in [configured, disabled, empty, another_empty]:
        qtbot.addWidget(widget)
    index = configured.model.index(0, 0)
    assert not configured.model.data(index, Qt.ItemDataRole.DecorationRole).isNull()
    assert (
        disabled.model.data(disabled.model.index(0, 0), Qt.ItemDataRole.DecorationRole)
        is None
    )
    assert empty.model.rowCount() == 0
    assert empty.model._data is not another_empty.model._data


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


@pytest.mark.parametrize(
    "icons, error",
    [
        ({"done": "SP_NotAnIcon"}, ValueError),
        ({"done": "__doc__"}, TypeError),
        ({"done": 123}, TypeError),
        ({1: "SP_DialogApplyButton"}, TypeError),
        ([], TypeError),
    ],
)
def test_mark_list_invalid_icon_config(qtbot, icons, error):
    """Invalid icon mappings report errors instead of silently hiding marks."""
    with pytest.raises(error):
        MarkList({"item": "done"}, mark_icons=icons)


def test_assign_widget_updates_marks(qtbot):
    """Assignments keep membership marks, including empty property values."""
    assignments = {"one": ""}
    widget = AssignWidget(["one", "two"], ["property"], assignments)
    qtbot.addWidget(widget)
    assert widget.items_w.model._data == {"one": True, "two": False}
    widget.items_w.select(["two"])
    widget.props_w.view.setCurrentIndex(widget.props_w.model.index(0, 0))
    widget.assign()
    assert assignments == {"one": "", "two": "property"}
    assert widget.items_w.model._data == {"one": True, "two": True}


def test_bad_channel_marks_refresh(qtbot):
    """Saving even an empty bad-channel selection marks the file as assigned."""
    from mne_nodes.gui.loading_widgets import SubBadsWidget

    marks = MarkList({"one": True, "two": False})
    qtbot.addWidget(marks)
    project = SimpleNamespace(all_meeg=["one", "two"], meeg_bad_channels={"one": []})
    current = Mock()
    current.set_bad_channels.side_effect = lambda channels: (
        project.meeg_bad_channels.update({"two": channels})
    )
    state = SimpleNamespace(
        pr=project, current_obj=current, bad_chkbts={}, files_widget=marks
    )
    SubBadsWidget.bad_ckbx_assigned(state)
    assert project.meeg_bad_channels["two"] == []
    assert marks.model._data == {"one": True, "two": True}


def test_ica_marks_refresh(qtbot):
    """ICA marks refresh for both checkbox and plot-based assignments."""
    from mne_nodes.gui.loading_widgets import ICASelect

    marks = MarkList({"one": True, "two": False})
    qtbot.addWidget(marks)
    project = SimpleNamespace(all_meeg=["one", "two"], meeg_ica_exclude={"one": []})
    state = SimpleNamespace(
        pr=project,
        current_obj=SimpleNamespace(name="two"),
        chkbxs={},
        file_list=marks,
        set_chkbx_enable=Mock(),
        update_chkbxs=Mock(),
    )
    ICASelect.component_selected(state)
    assert project.meeg_ica_exclude["two"] == []
    assert marks.model._data == {"one": True, "two": True}

    project.meeg_ica_exclude.pop("two")
    marks.replace_data({"one": True, "two": False})
    meeg = Mock()
    meeg.set_ica_exclude.side_effect = lambda components: (
        project.meeg_ica_exclude.update({"two": components})
    )
    ICASelect.get_selected_components(state, None, meeg, SimpleNamespace(exclude=[1]))
    assert marks.model._data == {"one": True, "two": True}
    state.update_chkbxs.assert_called_once()


def test_event_id_marks_refresh(qtbot):
    """Saving and copying event IDs refreshes the corresponding file marks."""
    from mne_nodes.gui.loading_widgets import EventIDGui, EvIDApply

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
