"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import pandas as pd
import pytest
from qtpy.QtCore import Qt

from tests._test_utils import toggle_checked_list_model

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
    ("ShallowTreeWidget", "group_tree"),
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
    from mne_nodes.gui.widgets.dict_widgets import EditDict, SimpleDict
    from mne_nodes.gui.widgets.list_widgets import CheckList, EditList, SimpleList
    from mne_nodes.gui.widgets.pandas_widgets import EditPandasTable, SimplePandasTable
    from mne_nodes.gui.widgets.tree_widgets import ShallowTreeWidget, TreeWidget

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


# Parameterized test for CheckList and related widgets with checking functionality
@pytest.mark.parametrize("widget_name, data_type", checklist_widgets)
def test_checklist_functionality(qtbot, widget_name, data_type, test_data):
    """Test CheckList and related widgets with checking functionality."""
    from mne_nodes.gui.widgets.list_widgets import CheckDictEditList, CheckList
    from mne_nodes.gui.widgets.tree_widgets import ShallowTreeWidget

    # Get the widget class
    widget_classes = {
        "CheckList": CheckList,
        "ShallowTreeWidget": ShallowTreeWidget,
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

    elif widget_name == "ShallowTreeWidget":
        checked = []
        widget = widget_class(data=original_data, checked=checked)
        widget.model.setData(
            widget.model.index(0, 0),
            Qt.CheckState.Checked,
            role=Qt.ItemDataRole.CheckStateRole,
        )
        assert checked == ["group_a"]
        widget.select_all()
        assert checked == ["group_a", "group_b"]
        widget.clear_all()
        assert checked == []

    elif widget_name == "CheckDictEditList":
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
