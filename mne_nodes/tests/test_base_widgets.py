"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import pandas as pd
import pytest
from qtpy.QtCore import Qt
from qtpy.QtCore import QItemSelectionModel

from mne_nodes.tests._test_utils import toggle_checked_list_model

# Define widget groups for parameterized testing
list_widgets = [
    ("SimpleList", "list"),
    ("EditList", "list"),
    ("CheckList", "checklist"),
]

dict_widgets = [("SimpleDict", "dict"), ("EditDict", "dict")]

table_widgets = [("SimplePandasTable", "dataframe"), ("EditPandasTable", "dataframe")]

tree_widgets = [("TreeWidget", "tree_dict"), ("ShallowTreeWidget", "group_tree")]

checklist_widgets = [
    ("CheckList", "checklist"),
    ("CheckDictList", "checkdict"),
    ("CheckDictEditList", "checkdict"),
]


# Test data for different widget types
@pytest.fixture
def test_data():
    return {
        "list": ["item1", "item2", "item3"],
        "checklist": ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"],
        "checkdict": ["item1", "item2", "item3"],
        "dict": {"key1": "value1", "key2": "value2", "key3": "value3"},
        "dataframe": pd.DataFrame({"A": [1, 2, 3], "B": [4, 5, 6], "C": [7, 8, 9]}),
        "tree_dict": {
            "level1_a": {"level2_a": "value_a", "level2_b": "value_b"},
            "level1_b": {"level2_c": {"level3_a": "deep_value"}, "level2_d": "value_d"},
        },
        "group_tree": {"group_a": ["item_a1", "item_a2"], "group_b": ["item_b1"]},
    }


@pytest.fixture
def new_test_data():
    return {
        "list": ["new1", "new2"],
        "checklist": ["x", "y", "z"],
        "checkdict": ["new1", "new2"],
        "dict": {"new_key1": "new_value1", "new_key2": "new_value2"},
        "dataframe": pd.DataFrame({"X": [10, 20], "Y": [30, 40]}),
        "tree_dict": {"new_level1": {"new_level2": "new_value"}},
        "group_tree": {"new_group": ["new_item"]},
    }


# Parameterized test for reference preservation and basic functionality
@pytest.mark.parametrize(
    "widget_name, data_type", list_widgets + dict_widgets + table_widgets + tree_widgets
)
def test_widget_reference_preservation(
    qtbot, widget_name, data_type, test_data, new_test_data
):
    """Test widget with reference preservation."""
    from mne_nodes.gui.base_widgets import (
        SimpleList,
        EditList,
        CheckList,
        SimpleDict,
        EditDict,
        SimplePandasTable,
        EditPandasTable,
        ShallowTreeWidget,
        TreeWidget,
    )

    # Get the widget class
    widget_class = {
        "SimpleList": SimpleList,
        "EditList": EditList,
        "CheckList": CheckList,
        "SimpleDict": SimpleDict,
        "EditDict": EditDict,
        "SimplePandasTable": SimplePandasTable,
        "EditPandasTable": EditPandasTable,
        "TreeWidget": TreeWidget,
        "ShallowTreeWidget": ShallowTreeWidget,
    }[widget_name]

    # Create original data
    original_data = test_data[data_type]

    # Create the widget with our data (CheckList needs checked parameter)
    if widget_name == "CheckList":
        checked = []
        widget = widget_class(data=original_data, checked=checked)
        # Verify checked list reference is preserved
        assert widget.model._checked is checked
    elif widget_name == "ShallowTreeWidget":
        checked = []
        widget = widget_class(data=original_data, checked=checked)
        assert widget.model._checked is checked
    else:
        widget = widget_class(data=original_data)

    qtbot.addWidget(widget)

    # Verify initial data
    assert widget.model._data is original_data

    # Test replace_data method
    new_data = new_test_data[data_type]
    widget.replace_data(new_data)
    assert widget.model._data is new_data

    # Test content_changed method
    if data_type == "list":
        original_data.append("item4")
    elif data_type == "dict":
        original_data["key4"] = "value4"
    elif data_type == "dataframe":
        original_data.loc[3] = [10, 11, 12]
    elif data_type == "tree_dict":
        original_data["level1_c"] = "new_value"
    elif data_type == "group_tree":
        original_data["group_c"] = ["item_c1"]

    widget.replace_data(original_data)
    widget.content_changed()

    # Verify data was updated
    if data_type == "list":
        assert "item4" in widget.model._data
    elif data_type == "dict":
        assert "key4" in widget.model._data
        assert widget.model._data["key4"] == "value4"
    elif data_type == "dataframe":
        assert widget.model._data.shape[0] == 4
        assert widget.model._data.iloc[3, 0] == 10
    elif data_type == "tree_dict":
        assert "level1_c" in widget.model._data
        assert widget.model._data["level1_c"] == "new_value"
    elif data_type == "group_tree":
        assert "group_c" in widget.model._data
        assert widget.model._data["group_c"] == ["item_c1"]


def test_shallow_tree_widget_checking(qtbot):
    """Test check handling in ShallowTreeWidget."""
    from mne_nodes.gui.base_widgets import ShallowTreeWidget

    data = {"g1": ["a", "b"], "g2": ["c"]}
    checked = []
    widget = ShallowTreeWidget(data=data, checked=checked)
    qtbot.addWidget(widget)

    assert widget.model._data is data
    assert widget.model._checked is checked

    first_group_index = widget.model.index(0, 0)
    widget.model.setData(
        first_group_index, Qt.CheckState.Checked, role=Qt.ItemDataRole.CheckStateRole
    )
    assert checked == ["g1"]

    widget.select_all()
    assert checked == ["g1", "g2"]

    widget.clear_all()
    assert checked == []


def test_shallow_tree_widget_editing(qtbot, monkeypatch):
    """Test add/remove editing operations in ShallowTreeWidget."""
    from mne_nodes.gui import base_widgets

    data = {"g1": ["a"], "g2": ["b", "c"]}
    checked = ["g2"]
    widget = base_widgets.ShallowTreeWidget(data=data, checked=checked)
    qtbot.addWidget(widget)

    monkeypatch.setattr(base_widgets, "get_user_input", lambda *_: "g3")
    widget.add_group()
    assert "g3" in data
    assert data["g3"] == []

    g2_index = widget.model.index(1, 0)
    widget.view.selectionModel().clearSelection()
    widget.view.selectionModel().select(g2_index, QItemSelectionModel.Select)
    widget.view.setCurrentIndex(g2_index)
    widget.remove_groups()
    assert "g2" not in data
    assert checked == []

    g1_index = widget.model.index(0, 0)
    widget.view.setCurrentIndex(g1_index)
    monkeypatch.setattr(base_widgets, "get_user_input", lambda *_: "new_item")
    widget.add_item()
    assert data["g1"][-1] == "new_item"

    g1_index = widget.model.index(0, 0)
    first_item_index = widget.model.index(0, 0, g1_index)
    widget.view.selectionModel().clearSelection()
    widget.view.selectionModel().select(first_item_index, QItemSelectionModel.Select)
    widget.view.setCurrentIndex(first_item_index)
    widget.remove_items()
    assert data["g1"] == ["new_item"]


def test_tree_widget_content_changed_rebuilds_view(qtbot):
    """TreeWidget should rebuild its internal tree after data changes."""
    from mne_nodes.gui.base_widgets import TreeWidget

    data = {"a": {"b": "c"}}
    widget = TreeWidget(data=data)
    qtbot.addWidget(widget)

    data["new_top"] = "value"
    widget.content_changed()

    keys = [widget.model.index(row, 0).data() for row in range(widget.model.rowCount())]
    assert "new_top" in keys


# Parameterized test for widget selection methods
@pytest.mark.parametrize(
    "widget_type, widget_names, data_type, select_params",
    [
        # List widgets
        (
            "list",
            ["SimpleList", "EditList"],
            "list",
            {
                "select_values": ["item1", "item3"],
                "expected_selected": ["item1", "item3"],
                "not_selected": ["item2"],
                "current_index": (1, 0),
                "expected_current": "item2",
            },
        ),
        # Dict widgets
        (
            "dict",
            ["SimpleDict", "EditDict"],
            "dict",
            {
                "select_keys": ["key1", "key3"],
                "select_values": ["value1", "value3"],
                "expected_selected": [("key1", "value1"), ("key3", "value3")],
                "expected_selected_count": 2,
                "current_index": (0, 0),
                "current_in_items": True,
            },
        ),
    ],
)
def test_widget_selection(
    qtbot, widget_type, widget_names, data_type, select_params, test_data
):
    """Test widget selection methods for different widget types."""
    from mne_nodes.gui.base_widgets import SimpleList, EditList, SimpleDict, EditDict

    # Map of widget names to classes
    widget_classes = {
        "SimpleList": SimpleList,
        "EditList": EditList,
        "SimpleDict": SimpleDict,
        "EditDict": EditDict,
    }

    for widget_name in widget_names:
        # Get the widget class
        widget_class = widget_classes[widget_name]

        # Create original data
        original_data = test_data[data_type]

        # Create the widget with our data
        widget = widget_class(data=original_data)
        qtbot.addWidget(widget)

        # Test get_current method
        if widget_type == "list":
            index = widget.model.createIndex(*select_params["current_index"])
        else:
            index = widget.model.index(*select_params["current_index"])

        widget.view.setCurrentIndex(index)
        current = widget.get_current()

        if "expected_current" in select_params:
            assert current == select_params["expected_current"]
        elif "current_in_items" in select_params and select_params["current_in_items"]:
            assert current in original_data.items()

        # Test select method
        if widget_type == "list":
            widget.select(select_params["select_values"])
        else:
            widget.select(select_params["select_keys"], select_params["select_values"])

        selected = widget.get_selected()

        if "expected_selected_count" in select_params:
            assert len(selected) == select_params["expected_selected_count"]

        for item in select_params["expected_selected"]:
            assert item in selected

        if "not_selected" in select_params:
            for item in select_params["not_selected"]:
                assert item not in selected


# Parameterized test for CheckList and related widgets with checking functionality
@pytest.mark.parametrize("widget_name, data_type", checklist_widgets)
def test_checklist_functionality(qtbot, widget_name, data_type, test_data):
    """Test CheckList and related widgets with checking functionality."""
    from mne_nodes.gui.base_widgets import CheckList, CheckDictList, CheckDictEditList

    # Get the widget class
    widget_classes = {
        "CheckList": CheckList,
        "CheckDictList": CheckDictList,
        "CheckDictEditList": CheckDictEditList,
    }
    widget_class = widget_classes[widget_name]

    # Create test data
    original_data = test_data[data_type]

    # Create the widget with appropriate parameters
    if widget_name == "CheckList":
        checked = []
        widget = widget_class(data=original_data, checked=checked)

        # Test basic reference preservation
        assert widget.model._data is original_data
        assert widget.model._checked is checked

        # Test select_all functionality
        widget.select_all()
        assert checked == original_data

        # Test clear_all functionality
        widget.clear_all()
        assert checked == []

        # Test individual item checking through model
        toggle_checked_list_model(widget.model, value=1, row=0)
        assert checked == [original_data[0]]

        toggle_checked_list_model(widget.model, value=0, row=0)
        assert checked == []

        toggle_checked_list_model(widget.model, value=1, row=1)
        assert checked == [original_data[1]]

        # Test replace_checked method
        new_checked = [original_data[2], original_data[3]]
        widget.replace_checked(new_checked)
        assert widget.model._checked is new_checked

    elif widget_name in ["CheckDictList", "CheckDictEditList"]:
        # For CheckDict widgets, we need a check_dict parameter
        check_dict = {"item1": "value1", "item3": "value3"}
        widget = widget_class(data=original_data, check_dict=check_dict)

        # Test basic reference preservation
        assert widget.model._data is original_data
        assert widget.model._check_dict is check_dict

        # Test replace_check_dict method
        new_check_dict = {"item2": "value2"}
        widget.replace_check_dict(new_check_dict)
        assert widget.model._check_dict is new_check_dict

    qtbot.addWidget(widget)


# Test for widget modification functionality
@pytest.mark.parametrize(
    "widget_class_name", ["EditList", "EditDict", "EditPandasTable"]
)
def test_widget_modification(qtbot, widget_class_name, test_data):
    """Test widget modification functionality for different widget types."""
    from mne_nodes.gui.base_widgets import EditList, EditDict, EditPandasTable

    # Map of widget class names to classes and data types
    widget_info = {
        "EditList": {"class": EditList, "data_type": "list"},
        "EditDict": {"class": EditDict, "data_type": "dict"},
        "EditPandasTable": {"class": EditPandasTable, "data_type": "dataframe"},
    }

    # Get the widget class and data type
    widget_class = widget_info[widget_class_name]["class"]
    data_type = widget_info[widget_class_name]["data_type"]

    # Create a copy of the original data
    original_data = test_data[data_type].copy()

    # Create the widget with our data
    widget = widget_class(data=original_data)
    qtbot.addWidget(widget)

    # Define modification steps based on widget type
    if data_type == "list":
        # Test adding a row
        original_data.append("__new0__")
        widget.content_changed()

        # Verify the assertions
        assert len(original_data) == 4
        assert "__new0__" in original_data
        assert widget.model._data is original_data

        # Test removing a row
        original_data.remove("item1")
        widget.content_changed()

        # Verify the assertions
        assert len(original_data) == 3
        assert "item1" not in original_data
        assert widget.model._data is original_data

        # Test editing an item
        index = original_data.index("item2")
        original_data[index] = "edited_item"
        widget.content_changed()

        # Verify the assertions
        assert "edited_item" in original_data
        assert "item2" not in original_data
        assert widget.model._data is original_data

    elif data_type == "dict":
        # Test adding a row
        original_data["__new0__"] = ""
        widget.content_changed()

        # Verify the assertions
        assert len(original_data) == 4
        assert "__new0__" in original_data
        assert widget.model._data is original_data

        # Test removing a row
        original_data.pop("key1")
        widget.content_changed()

        # Verify the assertions
        assert len(original_data) == 3
        assert "key1" not in original_data
        assert widget.model._data is original_data

        # Test editing an item
        original_data["key2"] = "edited_value"
        widget.content_changed()

        # Verify the assertions
        assert original_data["key2"] == "edited_value"
        assert widget.model._data is original_data

    elif data_type == "dataframe":
        # Test adding a row
        original_data.loc["new_row"] = [10, 11, 12]
        widget.content_changed()

        # Verify the assertions
        assert original_data.shape == (4, 3)
        assert "new_row" in original_data.index
        assert widget.model._data is original_data

        # Test adding a column
        original_data["new_col"] = [13, 14, 15, 16]
        widget.content_changed()

        # Verify the assertions
        assert original_data.shape == (4, 4)
        assert "new_col" in original_data.columns
        assert widget.model._data is original_data

        # Test removing a row
        original_data.drop(original_data.index[0], inplace=True)
        widget.content_changed()

        # Verify the assertions
        assert original_data.shape == (3, 4)
        assert widget.model._data is original_data

        # Test removing a column
        original_data.drop("A", axis=1, inplace=True)
        widget.content_changed()

        # Verify the assertions
        assert original_data.shape == (3, 3)
        assert "A" not in original_data.columns
        assert widget.model._data is original_data


# Non-parameterized tests for widgets with unique functionality


def test_timed_messagebox(qtbot):
    """Test TimedMessageBox."""
    from mne_nodes.gui.base_widgets import TimedMessageBox

    # Test text and countdown
    timed_messagebox = TimedMessageBox(timeout=2, step_length=100, text="Test")
    qtbot.addWidget(timed_messagebox)

    qtbot.waitForWindowShown(timed_messagebox)
    # For some reason Windows-CI seems to fail here,
    # maybe timed_messagebox.show() is blocking there
    assert timed_messagebox.text() == "Test\nTimeout: 2"

    # Test messagebox properly closes
    qtbot.wait(250)
    assert timed_messagebox.isHidden()

    # Test static methods
    # Test setting default button
    ans = TimedMessageBox.question(1, defaultButton=TimedMessageBox.StandardButton.Yes)
    qtbot.wait(150)
    assert ans == TimedMessageBox.StandardButton.Yes

    # Test setting buttons
    ans = TimedMessageBox.critical(
        1,
        buttons=TimedMessageBox.StandardButton.Save
        | TimedMessageBox.StandardButton.Cancel,
        defaultButton=TimedMessageBox.StandardButton.Cancel,
    )
    qtbot.wait(150)
    assert ans == TimedMessageBox.StandardButton.Cancel

    # Test setting no default button
    ans = TimedMessageBox.information(
        1,
        buttons=TimedMessageBox.StandardButton.Cancel,
        defaultButton=TimedMessageBox.StandardButton.NoButton,
    )
    qtbot.wait(150)
    assert ans is None


def test_progress_checklist(qtbot):
    """Test ProgressCheckList."""
    from mne_nodes.gui.base_widgets import CheckListProgress

    data = [f"item_{i}" for i in range(5)]
    checked = []
    progress_dict = {f"item_{i}": 30 for i in range(5)}

    clp = CheckListProgress(data=data, checked=checked, progress_dict=progress_dict)
    qtbot.addWidget(clp)
    clp.show()

    # Test initial state
    assert clp.model._data is data
    assert clp.model._checked is checked
    assert clp.progress_dict is not None
    qtbot.wait(1000)

    # Test checking items and progress update
    clp.update_progress("item_0", 50)
    assert clp.progress_dict["item_0"] == 50
    qtbot.wait(1000)

    for n in range(100):
        clp.update_progress("item_1", n)
        qtbot.wait(50)
    assert clp.progress_dict["item_1"] == 99
