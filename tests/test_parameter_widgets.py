"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import inspect
from pathlib import Path

import numpy as np
import pytest
from numpy.testing import assert_allclose

from mne_nodes.gui import parameter
from mne_nodes.gui.parameter import Param
from mne_nodes.gui.parameter.callable_gui import CallableGui, evaluate_function_code

gui_mapping = {
    "IntGui": "int",
    "FloatGui": "float",
    "StringGui": "string",
    "MultiTypeGui": "multi_type",
    "BoolGui": "bool",
    "DualTupleGui": "dual_tuple",
    "TupleGui": "tuple",
    "ComboGui": "combo",
    "ListGui": "list",
    "CheckListGui": "check_list",
    "DictGui": "dict",
    "SliderGui": "slider",
    "ColorGui": "color",
    "ColorDictGui": "color_dict",
    "PathGui": "path",
    "ArrayGui": "array",
    "SliceGui": "slice",
    "DataFrameGui": "dataframe",
    "CallableGui": "callable",
    "DateTimeGui": "datetime",
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


@pytest.mark.parametrize(
    ("data_type", "loaded", "expected"),
    [
        (float, 3, 3.0),
        (int, 3.0, 3),
        (int, -3.0, -3),
        (tuple, [1, "a"], (1, "a")),
        (list, (1, "a"), [1, "a"]),
        (tuple, [], ()),
        (list, (), []),
        (Path, "data", Path("data")),
        (str, Path("data"), "data"),
        (float | str, 3, 3.0),
        (tuple | dict, [1, "a"], (1, "a")),
        (int | float, 3, 3),
        (tuple | list, [1, "a"], [1, "a"]),
        (Path | str, "data", "data"),
    ],
)
def test_param_load_neighboring_types(qtbot, data_type, loaded, expected):
    """Loading and reloading preserve values by converting neighboring types."""
    data = {"value": loaded}
    gui = Param(data=data, name="value")
    qtbot.addWidget(gui)
    gui.data_type = data_type
    gui.read_param()

    assert gui.value == expected
    assert type(gui.value) is type(expected)


@pytest.mark.parametrize(
    ("data_type", "loaded", "default"),
    [
        (int, 3.5, 7),
        (int, float("nan"), 7),
        (int, float("inf"), 7),
        (int, float("-inf"), 7),
        (float, 10**400, 7.0),
        (float, True, 7.0),
        (bool, 1, False),
        (float, "3", 7.0),
        (list, "abc", []),
        (dict, [("key", "value")], {}),
        (Path, 3, Path("default")),
        (float, None, 7.0),
    ],
)
def test_param_load_incompatible_types(qtbot, caplog, data_type, loaded, default):
    """Unsafe or unrelated conversions still fall back with a warning."""
    gui = Param(data={"value": loaded}, name="value", default=default)
    qtbot.addWidget(gui)
    gui.data_type = data_type
    gui.read_param()

    assert gui.value == default
    assert type(gui.value) is type(default)
    assert "Using default value" in caplog.text


@pytest.mark.parametrize(
    ("gui_class", "loaded", "expected", "kwargs"),
    [
        (parameter.FloatGui, 3, 3.0, {}),
        (parameter.FloatGui, None, None, {"none_select": True}),
        (parameter.IntGui, 3.0, 3, {}),
        (parameter.ListGui, (1, 2), [1, 2], {}),
        (parameter.TupleGui, [1, 2], (1, 2), {}),
        (parameter.DualTupleGui, [1, 2], (1, 2), {}),
        (parameter.PathGui, "data", Path("data"), {}),
        (parameter.StringGui, Path("data"), "data", {}),
        (parameter.MultiTypeGui, 3, 3.0, {"types": ["float", "str"]}),
        (parameter.MultiTypeGui, [1, 2], (1, 2), {"types": ["tuple"]}),
        (parameter.MultiTypeGui, "data", Path("data"), {"types": ["float", "path"]}),
        (
            parameter.MultiTypeGui,
            Path("data"),
            Path("data"),
            {"types": ["str", "path"]},
        ),
    ],
)
def test_widget_load_neighboring_types(qtbot, gui_class, loaded, expected, kwargs):
    """Concrete widgets display and save converted values rather than defaults."""
    data = {"value": loaded}
    gui = gui_class(data=data, name="value", **kwargs)
    qtbot.addWidget(gui)

    assert gui.value == expected
    assert type(gui.value) is type(expected)
    gui._set_param()
    assert data["value"] == expected
    assert type(data["value"]) is type(expected)


@pytest.mark.parametrize(
    ("types", "loaded", "expected"),
    [
        (["int", "float"], 3, 3.0),
        (["float", "int"], 3.0, 3),
        (["list", "tuple"], [1, 2], (1, 2)),
        (["tuple", "list"], (1, 2), [1, 2]),
        (["str", "path"], "data", Path("data")),
        (["path", "str"], Path("data"), "data"),
        (["float", "int"], 3.5, 0),
    ],
)
def test_multitype_switch_neighboring_types(qtbot, types, loaded, expected):
    """Switching neighboring types converts the current value and persists it."""
    data = {"value": loaded}
    gui = parameter.MultiTypeGui(data=data, name="value", types=types)
    qtbot.addWidget(gui)
    gui.change_type(1)

    assert gui.value == expected
    assert type(gui.value) is type(expected)
    assert data["value"] == expected
    assert type(data["value"]) is type(expected)


def _check_param(gui, gui_name, value):
    if gui_name == "ArrayGui":
        assert_allclose(gui.value, value), f"Expected {value}, got {gui.value}"
    elif gui_name == "DataFrameGui":
        assert gui.value.equals(value), f"Expected {value}, got {gui.value}"
    elif gui_name == "CallableGui":
        expected_func, _ = evaluate_function_code(value)
        assert gui.value() == expected_func(), (
            f"Expected {expected_func()}, got {gui.value()}"
        )
    else:
        assert gui.value == value, f"Expected {value}, got {gui.value}"


@pytest.mark.parametrize("gui_name", list(gui_mapping.keys()))
def test_param_gui_round_trip(qtbot, gui_name, parameter_values, parameter_values_alt):
    """Each widget loads, stores, clears and clamps its parameter value."""
    gui_class = getattr(parameter, gui_name)
    gui_parameters = list(inspect.signature(gui_class).parameters) + list(
        inspect.signature(Param).parameters
    )
    kwargs = {key: value for key, value in gui_kwargs.items() if key in gui_parameters}
    parameters = {key: parameter_values[value] for key, value in gui_mapping.items()}
    gui = gui_class(data=parameters, name=gui_name, **kwargs)
    qtbot.addWidget(gui)
    _check_param(gui, gui_name, parameters[gui_name])

    new_param = parameter_values_alt[gui_mapping[gui_name]]
    gui.value = new_param
    _check_param(gui, gui_name, new_param)
    gui.value = None
    assert parameters[gui_name] is None

    if "max_val" in gui_parameters:
        size = 2 if gui_name == "DualTupleGui" else 1

        def as_value(number):
            return (number,) * size if size == 2 else number

        gui.value = as_value(1000)
        assert parameters[gui_name] == as_value(kwargs["max_val"])
        gui.value = as_value(-1000)
        assert parameters[gui_name] == as_value(kwargs["min_val"])


def test_array_gui_value_conversion(qtbot):
    """ArrayGui applies dtype, evaluates expressions and rejects bad input."""
    data = {"arr": np.zeros((2, 2), dtype=float)}
    gui = parameter.ArrayGui(data=data, name="arr", dtype=int)
    qtbot.addWidget(gui)
    assert gui.value.dtype == np.dtype(int)
    assert gui._table_model.setData(gui._table_model.index(0, 0), "3.7")
    assert gui.value[0, 0] == 3
    gui._expr_edit.setText("np.array([[1.8, 2.2]])")
    gui._on_expr_changed()
    assert_allclose(gui.value, np.array([[1, 2]]))
    assert gui.value.dtype == np.dtype(int)

    gui = parameter.ArrayGui(data=data, name="arr", none_select=True)
    qtbot.addWidget(gui)
    gui.set_param("np.ones((4, 5))")
    assert_allclose(gui.value, np.ones((4, 5)))
    gui.value = "np.ones((2, 3))"
    assert_allclose(gui.value, np.ones((2, 3)))
    gui.value = "not_a_valid_expression("
    assert gui.value is None
    gui = parameter.ArrayGui(data=data, name="arr", none_select=False)
    qtbot.addWidget(gui)
    gui.value = "not_a_valid_expression("
    assert_allclose(gui.value, np.empty((0, 0)))

    with pytest.raises(ValueError, match="at most 10 dimensions"):
        parameter.ArrayGui(data={"arr": np.zeros((1,) * 11)}, name="arr")


def test_evaluate_function_code():
    func, error = evaluate_function_code("def foo(x):\n    return x + 1\n")
    assert error is None
    assert func(2) == 3

    func, error = evaluate_function_code("def broken(:\n")
    assert func is None
    assert "Syntax error" in error

    func, error = evaluate_function_code("x = 1\n")
    assert func is None
    assert "No top-level function" in error

    func, error = evaluate_function_code("")
    assert func is None
    assert "No code entered" in error

    func, error = evaluate_function_code(
        "def foo(x):\n    return x + 1\n\n\ndef bar(x):\n    return x * 2\n"
    )
    assert func is None
    assert "Only one function/class definition is allowed" in error


def test_callable_gui_stores_code(qtbot):
    """Valid code is evaluated and persisted; broken code stores None."""
    data = {"func": "def foo(x):\n    return x + 1\n"}
    gui = CallableGui(data=data, name="func", none_select=True)
    qtbot.addWidget(gui)
    assert gui.value(1) == 2

    gui.editor.setPlainText("def bar(x):\n    return x * 2\n")
    gui._on_widget_changed()
    assert gui.value(3) == 6
    assert data["func"] == "def bar(x):\n    return x * 2\n"

    gui.editor.setPlainText("def broken(:\n")
    gui._on_widget_changed()
    assert gui.value is None
    assert data["func"] is None
