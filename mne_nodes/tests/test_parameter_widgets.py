"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import inspect

import numpy as np
import pytest
from numpy.testing import assert_allclose
from qtpy.QtCore import Qt

from mne_nodes.gui import parameter
from mne_nodes.gui.parameter import LabelGui, Param
from mne_nodes.tests._test_utils import toggle_checked_list_model

gui_mapping = {
    "IntGui": "int",
    "FloatGui": "float",
    "StringGui": "string",
    "MultiTypeGui": "multi_type",
    "FuncGui": "func",
    "BoolGui": "bool",
    "DualTupleGui": "tuple",
    "ComboGui": "combo",
    "ListGui": "list",
    "CheckListGui": "check_list",
    "DictGui": "dict",
    "SliderGui": "slider",
    "ColorGui": "color",
    "PathGui": "path",
    "ArrayGui": "array",
    "SliceGui": "slice",
    "DataFrameGui": "dataframe",
}

gui_kwargs = {
    "none_select": True,
    "min_val": -40,
    "max_val": 100,
    "step": 0.1,
    "return_integer": False,
    "unit": "ms",
    "options": ["a", "b", "c"],
    "keys": "DictGui",
    "editable": True,
}


def _check_param(gui, gui_name, value):
    if gui_name in ("FuncGui", "ArrayGui"):
        assert_allclose(gui.value, value), f"Expected {value}, got {gui.value}"
    elif gui_name == "DataFrameGui":
        assert gui.value.equals(value), f"Expected {value}, got {gui.value}"
    else:
        assert gui.value == value, f"Expected {value}, got {gui.value}"


@pytest.mark.parametrize("gui_name", list(gui_mapping.keys()))
@pytest.mark.parametrize("groupbox_layout", [True, False])
def test_basic_param_guis(
    qtbot, gui_name, groupbox_layout, parameter_values, parameter_values_alt
):
    gui_class = getattr(parameter, gui_name)
    gui_parameters = list(inspect.signature(gui_class).parameters) + list(
        inspect.signature(Param).parameters
    )
    kwargs = {key: value for key, value in gui_kwargs.items() if key in gui_parameters}
    kwargs["groupbox_layout"] = groupbox_layout
    parameters = {key: parameter_values[value] for key, value in gui_mapping.items()}
    gui = gui_class(data=parameters, name=gui_name, **kwargs)
    qtbot.addWidget(gui)

    # Check if value is correct
    _check_param(gui, gui_name, parameters[gui_name])

    # Check if paramChanged signal is emitted and value send correctly
    def test_slot(value):
        if gui_name in ("FuncGui", "ArrayGui") and value is not None:
            (
                assert_allclose(value, parameters[gui_name]),
                (f"Expected {parameters[gui_name]} from PyQtSignal, got {value}"),
            )
        elif gui_name == "DataFrameGui" and value is not None:
            assert value.equals(parameters[gui_name]), (
                f"Expected {parameters[gui_name]} from PyQtSignal, got {value}"
            )
        else:
            assert value == parameters[gui_name], (
                f"Expected {parameters[gui_name]} from PyQtSignal, got {value}"
            )

    gui.paramChanged.connect(test_slot)
    with qtbot.waitSignal(gui.paramChanged, timeout=1000):
        gui.value = parameters[gui_name]

    # Check if value changes correctly
    new_param = parameter_values_alt[gui_mapping[gui_name]]
    gui.value = new_param
    _check_param(gui, gui_name, new_param)

    # Set value to None
    gui.value = None
    assert parameters[gui_name] is None
    if groupbox_layout:
        assert not gui.group_box.isChecked()
    else:
        assert not gui.none_chkbx.isChecked()

    # Uncheck groupbox (old value should be restored)
    if groupbox_layout:
        gui.group_box.setChecked(True)
    else:
        gui.none_chkbx.setChecked(True)
    _check_param(gui, gui_name, new_param)

    # Test min/max values
    if "max_val" in gui_parameters:
        if gui_name == "DualTupleGui":
            value = (1000, 1000)
            neg_value = (-1000, -1000)
            max_val = (kwargs["max_val"], kwargs["max_val"])
            min_val = (kwargs["min_val"], kwargs["min_val"])
        else:
            value = 1000
            neg_value = -1000
            max_val = kwargs["max_val"]
            min_val = kwargs["min_val"]
        gui.value = value
        assert parameters[gui_name] == max_val
        # less than min
        gui.value = neg_value
        assert parameters[gui_name] == min_val

    # Test return integer for BoolGui
    if "return_integer" in gui_parameters:
        gui.return_integer = True
        gui.value = True
        assert gui.value == 1

    # Test ComboGui editing
    if gui_name == "ComboGui":
        gui.param_widget.lineEdit().setText("new_value")
        qtbot.keyClick(gui.param_widget, Qt.Key.Key_Return)
        assert gui.value == "new_value"

    # Test MultiTypeGui
    if gui_name == "MultiTypeGui":
        # Check if changing type works
        kwargs["type_kwargs"] = {}
        for gui_type, type_gui_name in gui.gui_types.items():
            type_class = getattr(parameter, type_gui_name)
            gui_parameters = list(inspect.signature(type_class).parameters) + list(
                inspect.signature(Param).parameters
            )
            t_kwargs = {
                key: value for key, value in gui_kwargs.items() if key in gui_parameters
            }
            kwargs["type_kwargs"][gui_type] = t_kwargs
        gui = gui_class(data=parameters, name=gui_name, **kwargs)
        for type_idx, (gui_type, type_gui_name) in enumerate(gui.gui_types.items()):
            gui.change_type(type_idx)
            gui.value = parameters[type_gui_name]
            assert gui.value == parameters[type_gui_name]


def test_array_gui_large_array(qtbot):
    """ArrayGui must construct without error for a large 3-D array.

    Only the model is exercised here — no actual table cells are rendered,
    so this validates the spinbox navigation path stays O(1) in array size.
    """
    big = np.zeros((300, 200, 50))
    data = {"arr": big}
    gui = parameter.ArrayGui(data=data, name="arr")
    qtbot.addWidget(gui)

    # Three dimensions: one QSpinBox for axis 0
    assert len(gui._spinboxes) == 1
    assert gui._spinboxes[0].maximum() == 299

    # Navigate to last slice — model must report correct shape
    gui._spinboxes[0].setValue(299)
    assert gui._table_model.rowCount() == 200
    assert gui._table_model.columnCount() == 50


def test_array_gui_ten_dimensions(qtbot):
    """ArrayGui provides a selector for every dimension beyond the table."""
    data = {"arr": np.zeros((2,) * 10)}
    gui = parameter.ArrayGui(data=data, name="arr")
    qtbot.addWidget(gui)

    assert gui._display_arr is not None
    assert gui._display_arr.ndim == 10
    assert len(gui._spinboxes) == 8

    for spinbox in gui._spinboxes:
        spinbox.setValue(1)

    assert gui._table_model.rowCount() == 2
    assert gui._table_model.columnCount() == 2


def test_array_gui_rejects_more_than_ten_dimensions(qtbot):
    """ArrayGui raises an error instead of reshaping unsupported arrays."""
    data = {"arr": np.zeros((1,) * 11)}

    with pytest.raises(ValueError, match="at most 10 dimensions"):
        parameter.ArrayGui(data=data, name="arr")


def test_array_gui_expr_mode(qtbot):
    """Switching to expr mode evaluates numpy expressions correctly."""
    data = {"arr": np.zeros((2, 3))}
    gui = parameter.ArrayGui(data=data, name="arr")
    qtbot.addWidget(gui)

    # Switch to expr mode
    gui._mode_cmbx.setCurrentIndex(1)
    gui._on_mode_changed(1)

    # Type a numpy expression and trigger evaluation
    gui._expr_edit.setText("np.ones((4, 5))")
    gui._on_expr_changed()

    assert gui.value is not None
    assert_allclose(gui.value, np.ones((4, 5)))


@pytest.mark.parametrize("setter", ["set_param", "value"])
def test_array_gui_string_expression(qtbot, setter):
    """Setting a string expression via set_param/value evaluates it via eval_param.

    An invalid expression must fall back to None if none_select is True, or to an
    empty array otherwise.
    """
    data = {"arr": np.zeros((2, 3))}
    gui = parameter.ArrayGui(data=data, name="arr", none_select=True)
    qtbot.addWidget(gui)

    def set_value(value):
        if setter == "set_param":
            gui.set_param(value)
        else:
            gui.value = value

    # Valid expression should be evaluated
    set_value("np.ones((4, 5))")
    assert gui.value is not None
    assert_allclose(gui.value, np.ones((4, 5)))

    # Invalid expression should fall back to None when none_select is True
    set_value("not_a_valid_expression(")
    assert gui.value is None

    # Invalid expression should fall back to an empty array when none_select is False
    gui_no_none = parameter.ArrayGui(data=data, name="arr", none_select=False)
    qtbot.addWidget(gui_no_none)
    gui_no_none.value = "not_a_valid_expression("
    assert_allclose(gui_no_none.value, np.empty((0, 0)))


@pytest.mark.skip(reason="temporarily disabled")
def test_label_gui(qtbot, ct):
    """Test opening label-gui without error."""

    # Add start labels
    ct.parameters["Default"]["test_labels"] = [
        "insula-lh",
        "postcentral-lh",
        "lh.BA1-lh",
    ]

    label_gui = LabelGui(data=ct, name="test_labels", default=[])
    qtbot.addWidget(label_gui)

    # Check start labels
    assert label_gui.param_value == ["insula-lh", "postcentral-lh", "lh.BA1-lh"]

    # Push edit button
    label_gui.param_widget.click()
    dlg = label_gui._dialog

    # Test start labels in checked
    assert ["insula-lh", "postcentral-lh"] == dlg._selected_parc_labels
    assert "lh.BA1-lh" in dlg._selected_extra_labels

    # Open Parc-Picker
    dlg.choose_parc_bt.click()
    parc_plot = dlg._parc_picker._renderer.plotter
    # Select "aparc" parcellation
    dlg.parcellation_cmbx.setCurrentText("aparc")
    dlg._parc_changed()  # Only triggered by mouse click with .activated
    # Check if start labels are shown
    assert "insula-lh" in dlg._parc_picker._shown_labels
    assert "postcentral-lh" in dlg._parc_picker._shown_labels
    # Add label by clicking on plot
    qtbot.mouseClick(
        parc_plot, Qt.MouseButton.LeftButton, pos=parc_plot.rect().center(), delay=100
    )
    assert "supramarginal-rh" in dlg._selected_parc_labels
    # Remove label by clicking on plot
    qtbot.mouseClick(
        parc_plot, Qt.MouseButton.LeftButton, pos=parc_plot.rect().center(), delay=100
    )
    assert "superiorfrontal-rh" not in dlg._selected_parc_labels
    # Add label by selecting from list
    toggle_checked_list_model(dlg.parc_label_list.model, value=1, row=5)
    assert "caudalmiddlefrontal-rh" in dlg._parc_picker._shown_labels
    toggle_checked_list_model(dlg.parc_label_list.model, value=0, row=5)
    assert "caudalmiddlefrontal-rh" not in dlg._parc_picker._shown_labels

    # Trigger subject changed (only fsaverage available), should not change anything
    dlg._subject_changed()
    parc_plot = dlg._parc_picker._renderer.plotter
    assert ["insula-lh", "postcentral-lh"] == dlg._selected_parc_labels
    assert "lh.BA1-lh" in dlg._selected_extra_labels

    # Open Extra-Picker
    dlg.choose_extra_bt.click()
    # Check if start labels are shown
    assert "lh.BA1-lh" in dlg._extra_picker._shown_labels

    # Change parcellation
    dlg.parcellation_cmbx.setCurrentText("aparc_sub")
    dlg._parc_changed()  # Only triggered by mouse click with .activated
    # Add label by clicking on plot
    qtbot.mouseClick(
        parc_plot, Qt.MouseButton.LeftButton, pos=parc_plot.rect().center(), delay=100
    )
    assert "supramarginal_9-rh" in dlg._selected_parc_labels
    # Add label by selecting from list
    toggle_checked_list_model(dlg.parc_label_list.model, value=1, row=0)
    assert "bankssts_1-lh" in dlg._selected_parc_labels

    final_selection = [
        "insula-lh",
        "postcentral-lh",
        "supramarginal_9-rh",
        "bankssts_1-lh",
        "lh.BA1-lh",
    ]
    # Check display widget
    assert dlg.selected_display.model._data == final_selection

    # Add all labels
    dlg.close()
    assert label_gui.param_value == final_selection
