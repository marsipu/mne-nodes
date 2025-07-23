"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import logging
from ast import literal_eval
from copy import copy
from functools import partial
from math import log10
from pathlib import Path
from types import NoneType

import mne
import numpy as np
import pandas as pd
from mne_qt_browser._pg_figure import _get_color
from qtpy import compat
from qtpy.QtCore import Qt, Signal
from qtpy.QtGui import QFontDatabase, QFont, QPixmap
from qtpy.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    QDockWidget,
    QTabWidget,
    QScrollArea,
    QMessageBox,
    QColorDialog,
)
from vtkmodules.vtkCommonCore import vtkCommand
from vtkmodules.vtkRenderingCore import vtkCellPicker

from mne_nodes import iswin
from mne_nodes.gui.base_widgets import (
    CheckList,
    EditDict,
    EditList,
    SimpleList,
    SimpleDialog,
    ComboBox,
)
from mne_nodes.gui.dialogs import CheckListDlg
from mne_nodes.gui.gui_utils import (
    get_std_icon,
    center,
    set_app_theme,
    set_app_font,
    get_user_input,
)
from mne_nodes.pipeline.controller import Controller
from mne_nodes.pipeline.exception_handling import get_exception_tuple
from mne_nodes.pipeline.execution import WorkerDialog
from mne_nodes.pipeline.loading import FSMRI
from mne_nodes.pipeline.settings import Settings


class Param(QWidget):
    """Base-Class Parameter-GUIs, not to be called directly Inherited Clases
    should have "Gui" in their name to get identified correctly.

    Attributes
    ----------
    paramChanged : Signal
        This signal is emmited when the parameter changes.
    Methods
    -------
    init_ui(layout=None)
        Base layout initialization, which adds the given layout to a
        group-box with the parameters name if groupbox_layout is enabled.
        Else the layout will be horizontal with a QLabel for the name.
    """

    data_type = object
    paramChanged = Signal(object)

    def __init__(
        self,
        data,
        name,
        alias=None,
        default=None,
        param_unit=None,
        groupbox_layout=True,
        none_select=False,
        description=None,
    ):
        """
        Parameters
        ----------
        data : dict | Controller | QSettings
            The data-structure, in which the value of the parameter is stored
            (depends on the scenario how the Parameter-Widget is used,
             e.g. displaying parameters from Project or displaying Settings
             from Main-Window).
        name : str
            The name of the key, which stores the value in the data-structure.
        alias : str | None
            An optional alias-name for the parameter for display
            (if you want to use a name, which is more readable, but can't or
            shouldn't be used as a key in Python).
        default : object
            The default value depending on GUI-Type.
        param_unit : str | None
            Supply an optional suffix with the name of the unit.
        groupbox_layout : bool
            If a groupbox should be used as layout
            (otherwise it is just a label), if None no label
        none_select : bool
            Set True if it should be possible to set the value to None
            by unchecking the GroupBox (on the left of the name).
        description : str | None
            Supply an optional description for the parameter,
            which will displayed as a Tool-Tip when the mouse
            is hovered over the Widget.
        """

        super().__init__()
        self.data = data
        self.name = name
        self.alias = alias if alias else self.name
        self._value = None
        self.default = default
        self.param_unit = param_unit
        self.groupbox_layout = groupbox_layout
        self.none_select = none_select
        self.description = description
        if description is not None:
            self.setToolTip(description)
        self.group_box = None
        self.none_chkbx = None
        self.param_layout = None

        # Load initial value from data source
        self._value = self._load_from_data(self.name)

    @property
    def value(self):
        """Get the current parameter value."""
        return self._value

    @value.setter
    def value(self, new_value):
        """Set the parameter value and update GUI and data source."""
        self._value = new_value
        self._update_param()

    def _update_param(self):
        self._update_gui()
        self._save_to_data(self.name, self._value)
        self.paramChanged.emit(self._value)

    def set_value(self, value):
        """Set the value by function call, e.g. as a slot."""
        self.value = value

    def _load_from_data(self, name):
        """Load parameter value from the data source."""
        # get data from Parameters in Controller
        if isinstance(self.data, Controller):
            value = self.data.parameter(name)
        # get data from dictionary
        elif isinstance(self.data, dict):
            value = self.data.get(name, self.default)
        # get data from QSettings
        elif isinstance(self.data, Settings) and name in self.data.childKeys():
            value = self.data.value(name)
        else:
            logging.warning(
                f"Parameter {name} not found in data source, using default value."
            )
            value = self.default

        # Validate data type
        data_types = (
            self.data_type if isinstance(self.data_type, list) else [self.data_type]
        )
        if self.none_select:
            data_types.append(NoneType)
        if not any([isinstance(value, dt) for dt in data_types]):
            raise RuntimeError(
                f"Data for {name} has to be of type {self.data_type}, "
                f"but is of type {type(value)} instead!"
            )
        return value

    def _save_to_data(self, name, value):
        """Save parameter value to the data source."""
        if isinstance(self.data, Controller):
            self.data.parameters[self.data.parameter_preset][name] = self._value
        elif isinstance(self.data, dict):
            self.data[name] = self._value
        elif isinstance(self.data, Settings):
            self.data.setValue(name, self._value)

    def _update_gui(self):
        """Update GUI widgets to reflect current parameter value."""
        self._check_none_state()
        if self._value is not None:
            self._set_widget_value(self._value)

    def _get_widget_value(self):
        """Get value from GUI widget.

        Should be overridden by child classes.
        """
        pass

    def _set_widget_value(self, value):
        """Set value to GUI widget.

        Should be overridden by child classes.
        """
        pass

    def _on_widget_changed(self):
        """Called when GUI widget value changes."""
        if self.none_select and not self._is_enabled():
            self.value = None
        else:
            widget_value = self._get_widget_value()
            if widget_value != self._value:
                self.value = widget_value

    def _is_enabled(self):
        """Check if the parameter widget is enabled (for none_select
        functionality)."""
        if self.groupbox_layout and self.group_box:
            return self.group_box.isChecked()
        elif self.none_chkbx:
            return self.none_chkbx.isChecked()
        return True

    def init_ui(self, layout):
        """Base layout initialization, which adds the given layout to a group-
        box with the parameters name if groupbox_layout is enabled.

        Else the layout will be horizontal with a QCheckbox/QLabel for
        the name.
        """
        self.param_layout = layout
        main_layout = QHBoxLayout()
        if self.groupbox_layout:
            self.group_box = QGroupBox(self.alias)
            self.group_box.setLayout(layout)

            if self.none_select:
                self.group_box.setCheckable(True)
                self.group_box.toggled.connect(self._on_none_changed)
            else:
                self.group_box.setCheckable(False)
            main_layout.addWidget(self.group_box)
        else:
            if self.none_select:
                self.none_chkbx = QCheckBox(self.alias)
                self.none_chkbx.checkStateChanged.connect(self._on_none_changed)
                main_layout.addWidget(self.none_chkbx)
            else:
                name_label = QLabel(self.alias)
                main_layout.addWidget(name_label)
            main_layout.addLayout(layout)

        self.setLayout(main_layout)
        self._update_gui()

    def _on_none_changed(self, checked=None):
        """Handle none selection checkbox/groupbox state changes."""
        if checked == Qt.Checked or checked is True:
            self._set_enabled(True)
            # Restore previous value or get current widget value
            if self._value is None:
                self.value = self._get_widget_value()
        else:
            self.value = None
            self._set_enabled(False)

    def _set_enabled(self, enabled):
        """Enable/disable parameter layout widgets."""
        if not self.groupbox_layout:
            if self.param_layout is not None:
                for i in range(self.param_layout.count()):
                    widget = self.param_layout.itemAt(i).widget()
                    if widget is not None:
                        widget.setEnabled(enabled)

    def _check_none_state(self):
        """Check and update none selection state."""
        if self.none_select:
            if self._value is None:
                if self.groupbox_layout and self.group_box:
                    self.group_box.setChecked(False)
                elif self.none_chkbx:
                    self.none_chkbx.setChecked(False)
                    self._set_enabled(False)
            else:
                if self.groupbox_layout and self.group_box:
                    self.group_box.setChecked(True)
                elif self.none_chkbx:
                    self.none_chkbx.setChecked(True)
                    self._set_enabled(True)


class IntGui(Param):
    """A GUI for Integer-Parameters."""

    data_type = int

    def __init__(self, min_val=0, max_val=1000, special_value_text=None, **kwargs):
        """
        Parameters
        ----------
        min_val : int
            Set the minimumx value, defaults to 0.
        max_val : int
            Set the maximum value, defaults to 100.
        special_value_text : str | None
            Supply an optional text for the value 0.
        **kwargs
            All the parameters fo :method:`~Param.__init__` go here.
        """

        super().__init__(**kwargs)

        self.param_widget = QSpinBox()
        self.param_widget.setMinimum(min_val)
        self.param_widget.setMaximum(max_val)
        self.param_widget.setToolTip(f"MinValue = {min_val}\nMaxValue = {max_val}")
        if special_value_text:
            self.param_widget.setSpecialValueText(special_value_text)
        if self.param_unit:
            self.param_widget.setSuffix(f" {self.param_unit}")
        self.param_widget.valueChanged.connect(self._on_widget_changed)

        layout = QHBoxLayout()
        layout.addWidget(self.param_widget)
        self.init_ui(layout)

    def _set_widget_value(self, value):
        self.param_widget.setValue(int(value))

    def _get_widget_value(self):
        return self.param_widget.value()


class FloatGui(Param):
    """A GUI for Float-Parameters."""

    data_type = float

    def __init__(self, min_val=-1000.0, max_val=1000.0, step=0.1, decimals=2, **kwargs):
        """
        Parameters
        ----------
        min_val : int | float
            Set the minimumx value, defaults to -100..
        max_val : int | float
            Set the maximum value, defaults to 100..
        step : int | float
            Set the step-size, defaults to 0.1.
        decimals : int
            Set the number of decimals of the value.
        **kwargs
            All the parameters fo :method:`~Param.__init__` go here.
        """

        super().__init__(**kwargs)
        self.param_widget = QDoubleSpinBox()
        self.param_widget.setMinimum(min_val)
        self.param_widget.setMaximum(max_val)
        self.param_widget.setSingleStep(step)
        self.param_widget.setDecimals(decimals)
        self.param_widget.setToolTip(f"MinValue = {min_val}\nMaxVal = {max_val}")
        if self.param_unit:
            self.param_widget.setSuffix(f" {self.param_unit}")
        self.param_widget.valueChanged.connect(self._on_widget_changed)

        layout = QHBoxLayout()
        layout.addWidget(self.param_widget)
        self.init_ui(layout)

    def _set_widget_value(self, value):
        self.param_widget.setValue(float(value))

    def _get_widget_value(self):
        return self.param_widget.value()


class StringGui(Param):
    """A GUI for String-Parameters."""

    data_type = str

    def __init__(self, **kwargs):
        """

        Parameters
        ----------
        **kwargs
            All the parameters fo :method:`~Param.__init__` go here.
        """

        super().__init__(**kwargs)
        self.param_widget = QLineEdit()
        self.param_widget.textChanged.connect(self._on_widget_changed)
        layout = QHBoxLayout()
        layout.addWidget(self.param_widget)
        if self.param_unit is not None:
            layout.addWidget(QLabel(self.param_unit))
        self.init_ui(layout)

    def _set_widget_value(self, value):
        self.param_widget.setText(value)

    def _get_widget_value(self):
        return self.param_widget.text()


def _eval_param(param_exp):
    try:
        return eval(param_exp, {"np": np})
    except (NameError, SyntaxError, ValueError, TypeError):
        return None


class FuncGui(Param):
    """A GUI for Parameters defined by small functions, e.g from numpy."""

    data_type = object

    def __init__(self, **kwargs):
        """
        Parameters
        ----------
        **kwargs
            All the parameters fo :method:`~Param.__init__` go here.
        """
        super().__init__(**kwargs)
        self.param_exp = None
        self.param_widget = QLineEdit()
        self.param_widget.setToolTip(
            "Use of functions also allowed "
            "(from already imported modules + numpy as np)\n"
            "Be carefull as everything entered will be executed!"
        )
        self.param_widget.editingFinished.connect(self._on_widget_changed)
        self.display_widget = QLabel()
        func_layout = QGridLayout()
        label1 = QLabel("Insert Function/Value here")
        label2 = QLabel("Output")
        func_layout.addWidget(label1, 0, 0)
        func_layout.addWidget(label2, 0, 1, 1, 2)
        func_layout.addWidget(self.param_widget, 1, 0)
        func_layout.addWidget(self.display_widget, 1, 1)
        if self.param_unit:
            func_layout.addWidget(QLabel(self.param_unit))
        self.init_ui(func_layout)

    def _set_widget_value(self, value):
        # For FuncGui, we need to handle both expression and evaluated value
        if hasattr(self, "param_exp") and self.param_exp is not None:
            self.param_widget.setText(str(self.param_exp))
            self.display_widget.setText(str(value)[:20])
        else:
            self.param_widget.setText(str(value))
            self.display_widget.setText(str(value)[:20])

    def _get_widget_value(self):
        self.param_exp = self.param_widget.text()
        value = _eval_param(self.param_exp)
        self.display_widget.setText(str(value)[:20])
        return value

    def _load_from_data(self, name):
        """Load both the expression and evaluated value from data source."""
        # Load the evaluated value first
        real_value = super()._load_from_data(name)

        # Load the expression (stored with "_exp" suffix)
        exp_value = super()._load_from_data(name + "_exp")

        # Set expression if it exists and is not empty
        if exp_value != "" and exp_value is not None:
            self.param_exp = exp_value
        else:
            self.param_exp = real_value

        return real_value

    def _save_to_data(self, name):
        """Save both the expression and evaluated value to data source."""
        # Save the evaluated value
        super()._save_to_data(name, self.value)

        # Save the expression with "_exp" suffix
        exp_name = name + "_exp"
        exp_value = self.param_exp if self.param_exp is not None else self._value
        super()._save_to_data(exp_name, exp_value)

    @property
    def value(self):
        """Get the current parameter value (evaluated result)."""
        return super().value

    @value.setter
    def value(self, new_value):
        """Set the parameter value.

        For FuncGui, this can be an expression or evaluated value.
        """
        if isinstance(new_value, str):
            # If it's a string, treat it as an expression
            self._value = _eval_param(new_value)
            self.param_exp = new_value
        else:
            # If it's already evaluated, use it directly
            self._value = new_value
            self.param_exp = str(new_value)

        self._update_gui()
        self._save_to_data()
        self.paramChanged.emit(self._value)


class BoolGui(Param):
    """A GUI for Boolean-Parameters."""

    data_type = bool

    def __init__(self, return_integer=False, **kwargs):
        """
        Parameters
        ----------
        return_integer : bool
            Set True to return an integer (0|1) instead of a boolean
            (e.g. useful for QSettings).
        **kwargs
            All the parameters fo :method:`~Param.__init__` go here.
        """
        super().__init__(**kwargs)
        self.return_integer = return_integer
        self.param_widget = QCheckBox()
        self.param_widget.toggled.connect(self._on_widget_changed)
        layout = QVBoxLayout()
        layout.addWidget(self.param_widget)
        self.init_ui(layout)

    def _set_widget_value(self, value):
        self.param_widget.setChecked(bool(value))

    def _get_widget_value(self):
        value = self.param_widget.isChecked()
        if self.return_integer:
            value = 1 if value else 0

        return value


class DualTupleGui(Param):
    """A GUI for two parameters in a tuple (e.g. for filters, limits etc.).

    It only supports integer and float values.
    """

    data_type = tuple

    def __init__(self, min_val=-1000.0, max_val=1000.0, step=0.1, **kwargs):
        """
        Parameters
        ----------
        min_val : int | float
            Set the minimumx value, defaults to -100..
        max_val : int | float
            Set the maximum value, defaults to 100..
        step : int | float
            Set the amount, one step takes.
        **kwargs
            All the parameters fo :method:`~Param.__init__` go here.
        """

        super().__init__(**kwargs)

        self.param_widget1 = QDoubleSpinBox()
        self.param_widget2 = QDoubleSpinBox()
        decimals = int(-log10(step))
        self.param_widget1.setDecimals(decimals)
        self.param_widget2.setDecimals(decimals)

        self._external_set = False

        self.param_widget1.setToolTip(
            f"MinValue = {min_val}\nMaxVal = {max_val}\nStep = {step}\n"
        )
        self.param_widget2.setToolTip(
            f"MinValue = {min_val}\nMaxVal = {max_val}\nStep = {step}\n"
        )

        self.param_widget1.setMinimum(min_val)
        self.param_widget1.setMaximum(max_val)
        self.param_widget1.setSingleStep(step)
        if self.param_unit:
            self.param_widget1.setSuffix(f" {self.param_unit}")
        self.param_widget1.valueChanged.connect(self._on_widget_changed)

        self.param_widget2.setMinimum(min_val)
        self.param_widget2.setMaximum(max_val)
        self.param_widget2.setSingleStep(step)
        if self.param_unit:
            self.param_widget2.setSuffix(f" {self.param_unit}")
        self.param_widget2.valueChanged.connect(self._on_widget_changed)
        tuple_layout = QHBoxLayout()
        tuple_layout.addWidget(self.param_widget1)
        tuple_layout.addWidget(self.param_widget2)
        self.init_ui(tuple_layout)

    def _set_widget_value(self, value):
        # Signal valueChanged is already emitted after first setValue,
        # which leads to second value being 0 without being
        # preserved in self.loaded_value
        if not len(value) == 2:
            raise ValueError(
                f"Expected a tuple of length 2, got {len(value)} elements."
            )
        else:
            self._external_set = True
            self.param_widget1.setValue(value[0])
            self.param_widget2.setValue(value[1])
            self._external_set = False

    def _get_widget_value(self):
        """Get the values from both spinboxes and return them as a tuple."""
        return self.param_widget1.value(), self.param_widget2.value()

    def _on_widget_changed(self):
        """Handle changes in the widget values."""
        if not self._external_set:
            # Only update if not set externally to avoid recursion
            super()._on_widget_changed()


class ComboGui(Param):
    """A GUI for a Parameter to select from a list of (string)-options."""

    data_type = str

    def __init__(self, options, raise_missing=False, **kwargs):
        """
        Parameters
        ----------
        options : list | dict
            Supply a list or a dictionary with the options to choose from.
            If supplied a dictionary, dictionary-values are
            taken as aliases for the keys. Only strings are allowed.
        raise_missing : bool
            Set to True, if an error should be raised when the value
            is not in the options.
        **kwargs
            All the parameters fo :method:`~Param.__init__` go here.
        """
        super().__init__(**kwargs)
        self.options = options
        self.raise_missing = raise_missing
        self._options_change = False
        self.param_widget = ComboBox(scrollable=False)
        self._init_options()
        self.param_widget.currentTextChanged.connect(self._on_widget_changed)
        layout = QHBoxLayout()
        layout.addWidget(self.param_widget)
        if self.param_unit is not None:
            layout.addWidget(QLabel(self.param_unit))
        self.init_ui(layout)

    def change_options(self, options):
        """Change the options of the ComboBox.

        Parameters
        ----------
        options : list | dict
            Supply a list or a dictionary with the options to choose from.
            If supplied a dictionary, dictionary-values are
            taken as aliases for the keys. Only strings are allowed.
        """
        self.options = options
        self._options_change = True
        self.param_widget.clear()
        self._init_options()
        self._options_change = False
        self._set_widget_value(self.value)

    def _init_options(self):
        if not self._options_change:
            for option in self.options:
                if isinstance(self.options, dict):
                    self.param_widget.addItem(str(self.options[option]))
                else:
                    self.param_widget.addItem(str(option))

    def _set_widget_value(self, value):
        # Check if value is str
        if not isinstance(value, str):
            value = str(value)
        # Check if value is in options
        options = (
            list(self.options.keys())
            if isinstance(self.options, dict)
            else self.options
        )
        if value not in options:
            if self.raise_missing:
                raise RuntimeError(f"{value} not in options for {self.name}.")
            else:
                old_value = value
                if self.default in options:
                    value = self.default
                else:
                    value = options[0]
                logging.warning(
                    f"{old_value} not in options for {self.name}, set to {value}."
                )
        if isinstance(self.options, dict):
            alias = self.options[value]
        self.param_widget.setCurrentText(alias)

    def _get_widget_value(self):
        text = self.param_widget.currentText()
        if isinstance(self.options, dict):
            if text not in self.options.values():
                if self.raise_missing:
                    raise RuntimeError(f"{text} not in options for {self.name}.")
                else:
                    value = list(self.options.values())[0]
            else:
                value = [
                    key
                    for key, value in self.options.items()
                    if value == self.param_widget.currentText()
                ][0]
        else:
            value = self.param_widget.currentText()

        return value


def convert_list_to_string(value, unit=None, string_length=30):
    """Convert a list to a string representation with optional unit and length
    limit."""
    if isinstance(value, list):
        if unit:
            val_str = ", ".join([f"{item} {unit}" for item in value])
        else:
            val_str = ", ".join([str(item) for item in value])
        if len(val_str) >= string_length:
            text = f"{val_str[:string_length]} ..."
        else:
            text = val_str
    else:
        text = str(value)
    return text


class ListGui(Param):
    """A GUI for as list."""

    data_type = list

    def __init__(self, value_string_length=30, **kwargs):
        """
        Parameters
        ----------
        value_string_length : int | None
            Set the limit of characters to which the value converted to a
            string will be displayed.
        **kwargs
            All the parameters fo :method:`~Param.__init__` go here.
        """

        super().__init__(**kwargs)
        self.value_string_length = value_string_length
        # Cache value to use after selecting None
        self.cached_value = None
        list_layout = QHBoxLayout()
        self.value_label = QLabel()
        list_layout.addWidget(self.value_label)
        self.param_widget = QPushButton("Edit")
        self.param_widget.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
        self.param_widget.clicked.connect(self.open_dialog)
        list_layout.addWidget(self.param_widget, alignment=Qt.AlignCenter)
        self.init_ui(list_layout)

    def open_dialog(self):
        """Open the dialog to edit the list."""
        dlg = SimpleDialog(
            EditList(self.value),
            self,
            title=f"Setting {self.alias}",
            window_title=self.alias,
        )
        dlg.finished.connect(self._update_param)

    def _set_widget_value(self, value):
        if value is not None:
            self.cached_value = value
        self.value_label.setText(
            convert_list_to_string(value, self.param_unit, self.value_string_length)
        )

    def _get_widget_value(self):
        if self.value is None:
            if self.cached_value is not None:
                value = self.cached_value
            else:
                value = []
            self.value_label.clear()
        else:
            value = self._value

        return value


class CheckListGui(Param):
    """A GUI to select items from a list of options."""

    data_type = list

    def __init__(self, options, value_string_length=30, one_check=False, **kwargs):
        """
        Parameters
        ----------
        options : list
            The items from which to choose
        value_string_length : int | None
            Set the limit of characters to which the value converted to a
            string will be displayed.
        one_check : bool
            Set to True, if only one item should be selectable
             (or use ComboGUI).
        **kwargs
            All the parameters fo :method:`~Param.__init__` go here.
        """

        if not isinstance(options, list) or len(options) == 0:
            options = ["Empty"]

        super().__init__(**kwargs)
        self.options = options
        self.value_string_length = value_string_length
        self.one_check = one_check
        # Cache value to use after selecting None
        self.cached_value = None
        check_list_layout = QHBoxLayout()
        self.value_label = QLabel()
        check_list_layout.addWidget(self.value_label)
        self.param_widget = QPushButton("Edit")
        self.param_widget.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
        self.param_widget.clicked.connect(self.open_dialog)
        check_list_layout.addWidget(self.param_widget)

        self.init_ui(check_list_layout)

    def open_dialog(self):
        """Open the dialog to edit the checklist."""
        dlg = SimpleDialog(
            CheckList(data=self.options, checked=self.value, one_check=self.one_check),
            self,
            title=f"Setting {self.alias}",
            window_title=self.alias,
        )
        dlg.finished.connect(self._update_param)

    def change_options(self, options):
        """Change the options of the CheckList.

        Parameters
        ----------
        options : list
            The items from which to choose.
        """
        self.options = options
        self._set_widget_value(self.value)

    def _set_widget_value(self, value):
        if value is not None:
            self.cached_value = value
        self.value_label.setText(
            convert_list_to_string(value, self.param_unit, self.value_string_length)
        )

    def _get_widget_value(self):
        if self.value is None:
            if self.cached_value:
                value = self.cached_value
            else:
                value = []
            self.value_label.clear()
        else:
            value = self._value

        return value


def convert_dict_to_string(value, unit=None, string_length=30):
    """Convert a dictionary to a string representation with optional unit and
    length limit."""
    if isinstance(value, dict):
        if unit:
            val_str = ", ".join([f"{k} {unit}: {v} {unit}" for k, v in value.items()])
        else:
            val_str = ", ".join([f"{k}: {v}" for k, v in value.items()])
        if len(val_str) >= string_length:
            text = f"{val_str[:string_length]} ..."
        else:
            text = val_str
    else:
        text = str(value)
    return text


class DictGui(Param):
    """A GUI for a dictionary."""

    data_type = dict

    def __init__(self, value_string_length=30, **kwargs):
        """

        Parameters
        ----------
        value_string_length : int | None
            Set the limit of characters to which the value converted
            to a string will be displayed.
        **kwargs
            All the parameters fo :method:`~Param.__init__` go here.
        """

        super().__init__(**kwargs)
        self.value_string_length = value_string_length
        # Cache value to use after setting value to None
        # with GroupBox-Checkbox
        self.cached_value = None

        dict_layout = QHBoxLayout()
        self.value_label = QLabel()
        dict_layout.addWidget(self.value_label)
        self.param_widget = QPushButton("Edit")
        self.param_widget.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
        self.param_widget.clicked.connect(self.open_dialog)
        dict_layout.addWidget(self.param_widget)
        self.init_ui(dict_layout)

    def open_dialog(self):
        """Open the dialog to edit the dictionary."""
        dlg = SimpleDialog(
            EditDict(self.value),
            self,
            title=f"Setting {self.alias}",
            window_title=self.alias,
        )
        dlg.finished.connect(self._update_param)

    def _set_widget_value(self, value):
        if value is not None:
            self.cached_value = value
        self.value_label.setText(
            convert_dict_to_string(value, self.param_unit, self.value_string_length)
        )

    def _get_widget_value(self):
        if self.value is None:
            if self.cached_value:
                value = self.cached_value
            else:
                value = {}
            self.value_label.clear()
        else:
            value = self.value

        return value


class SliderGui(Param):
    """A GUI to show a slider for Int/Float-Parameters."""

    data_type = [int, str]

    def __init__(self, min_val=0, max_val=100, step=1, tracking=True, **kwargs):
        """
        Parameters
        ----------
        min_val : int | float
            Set the minimumx value, defaults to 0.
        max_val : int | float
            Set the maximum value, defaults to 100..
        step : int | float
            Set the step-size, defaults to 1.
        tracking : bool
            Set True if values should be updated constantly while the slider
            is dragged (can cause crashes when heavyweight functions are
            connected to the ParamChanged-Signal).
        **kwargs
            All the parameters fo :method:`~Param.__init__` go here.
        """
        super().__init__(**kwargs)
        self.min_val = min_val
        self.max_val = max_val
        self.param_widget = QSlider()
        self.param_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.decimal_count = max(
            [
                len(str(value)[str(value).find(".") :]) - 1
                for value in [min_val, max_val, step]
            ]
        )
        if self.decimal_count > 0:
            self.param_widget.setMinimum(int(self.min_val * 10**self.decimal_count))
            self.param_widget.setMaximum(int(self.max_val * 10**self.decimal_count))
        else:
            self.param_widget.setMinimum(self.min_val)
            self.param_widget.setMaximum(self.max_val)
        self.param_widget.setSingleStep(int(step))
        self.param_widget.setOrientation(Qt.Horizontal)
        # Only change value when slider is released
        self.param_widget.setTracking(tracking)
        self.param_widget.setToolTip(
            f"MinValue = {min_val}\nMaxValue = {max_val}\nStep = {step}"
        )
        self.param_widget.valueChanged.connect(self._on_widget_changed)

        self.display_widget = QLineEdit()
        self.display_widget.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
        self.display_widget.setAlignment(Qt.AlignRight)
        self.display_widget.editingFinished.connect(self.display_edited)
        slider_layout = QHBoxLayout()
        slider_layout.addWidget(self.param_widget, stretch=10)
        slider_layout.addWidget(self.display_widget, stretch=1)
        if self.param_unit:
            slider_layout.addWidget(QLabel(self.param_unit))

        self.init_ui(slider_layout)

    def display_edited(self):
        try:
            new_value = literal_eval(self.display_widget.text())
        except (ValueError, SyntaxError):
            new_value = None
        if new_value:
            self.value = new_value
            self.param_widget.setValue(int(new_value * 10**self.decimal_count))

    def _set_widget_value(self, value):
        if value is not None:
            if self.decimal_count > 0:
                self.param_widget.setValue(int(value * 10**self.decimal_count))
            else:
                self.param_widget.setValue(value)
            self.display_widget.setText(str(value))

    def _get_widget_value(self):
        value = self.param_widget.value()
        if self.decimal_count > 0:
            value /= 10**self.decimal_count
        self.display_widget.setText(str(value))

        return value


class MultiTypeGui(Param):
    """A GUI which accepts multiple types of values in a single LineEdit."""

    data_type = [int, float, bool, str, list, dict, tuple]

    def __init__(self, type_selection=False, types=None, type_kwargs=None, **kwargs):
        """
        Parameters
        ----------
        type_selection : bool
            If True, the use can choose in a QComboBox which type they want
            to enter and then use the appropriate GUI. Else, the user can
            enter any type in a QLineEdit and the type will be inferred.
        types : list of str | None
            If type_selection is True, the type-selection will be limited
            to the given types (type-name as string).
        type_kwargs : dict | None
            Specify keyword-arguments as a dictionary for the different GUIs
            (look into their documentation),
            the key is the name of the GUI (e.g. IntGui).
        **kwargs
            All the parameters fo :method:`~Param.__init__` go here.
        """
        super().__init__(**kwargs)
        self.type_selection = type_selection
        self.types = types or [
            "int",
            "float",
            "bool",
            "str",
            "list",
            "dict",
            "tuple",
            "combo",
            "checklist",
            "slider",
        ]
        self.type_kwargs = type_kwargs or {}

        # A dictionary to map possible types with their GUI
        self.gui_types = {
            "int": "IntGui",
            "float": "FloatGui",
            "bool": "BoolGui",
            "str": "StringGui",
            "list": "ListGui",
            "dict": "DictGui",
            "tuple": "DualTupleGui",
            "combo": "ComboGui",
            "checklist": "CheckListGui",
            "slider": "SliderGui",
        }
        self.type_layout = QHBoxLayout()

        # Get current type (NoneType not allowed)
        self.param_type = type(self.value).__name__
        if self.param_type == "NoneType":
            self.param_type = self.types[0]

        if self.type_selection:
            self.param_widget = None
            self.type_cmbx = QComboBox()
            self.type_cmbx.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
            self.type_cmbx.addItems(self.types)
            self.type_cmbx.activated.connect(self.change_type)
            self.type_cmbx.setCurrentText(self.param_type)
            self.type_layout.addWidget(self.type_cmbx)
            self.add_type_gui()
        else:
            self.param_widget = QLineEdit()
            self.param_widget.textEdited.connect(self._on_widget_changed)
            self.type_display = QLabel()
            self.type_layout.addWidget(self.param_widget)
            self.type_layout.addWidget(self.type_display)
        self.init_ui(self.type_layout)

    def add_type_gui(self):
        gui_name = self.gui_types[self.param_type]

        # Load specifc keyword-arguments if given
        if gui_name in self.type_kwargs:
            kwargs = self.type_kwargs[gui_name]
        else:
            kwargs = {}

        # Set standard parameter-keyword-arguments as given to MultiTypeGui
        kwargs["data"] = self.data
        kwargs["name"] = self.name
        kwargs["alias"] = ""
        kwargs["default"] = self.default
        kwargs["groupbox_layout"] = False
        kwargs["none_select"] = False
        kwargs["description"] = self.description
        kwargs["param_unit"] = self.param_unit

        self.param_widget = globals()[gui_name](**kwargs)
        self.param_widget.value = self.value
        self.type_layout.addWidget(self.param_widget)

    def change_type(self, type_idx):
        # Set Param-Value to None to avoid conflicts
        # whith values from other types
        self.value = None

        old_widget = self.type_layout.itemAt(1)
        self.type_layout.removeItem(old_widget)
        try:
            old_widget.widget().deleteLater()
        except RuntimeError:
            logging.debug("Old widget already deleted")
        del old_widget, self.param_widget

        self.param_type = self.types[type_idx]

        self.add_type_gui()

    def _set_widget_value(self, value):
        if self.type_selection:
            self.param_widget.value = value
        elif value is not None:
            self.param_widget.setText(str(value))
            self.type_display.setText(f"Type: {type(value).__name__}")

    def _get_widget_value(self):
        if self.type_selection:
            value = self.param_widget.value
        else:
            text = self.param_widget.text()
            try:
                value = literal_eval(text)
                self.param_type = type(value).__name__
            except ValueError:
                value = text
                self.param_type = "str"
            except SyntaxError:
                value = None
                self.param_type = "error"
            self.type_display.setText(f"Type: {self.param_type}")

        return value


class LabelPicker(mne.viz.Brain):
    def __init__(
        self, paramdlg, parcellation, surface, selected, list_changed_slot, title
    ):
        super().__init__(
            paramdlg._fsmri.name,
            surf=surface,
            title=title,
            subjects_dir=paramdlg.ct.subjects_dir,
            background=(0, 0, 0),
        )
        self._renderer.plotter.show()
        self.paramdlg = paramdlg
        self.paramw = paramdlg.paramw

        self.parcellation = parcellation
        self.selected = selected
        self.list_changed_slot = list_changed_slot

        self._shown_labels = []

        # Title text
        self.add_text(0, 0.9, "", color="w", font_size=14, name="title")

        self._set_annotations(parcellation)
        self._init_picking()

        # Add selected labels
        for label_name in selected:
            hemi = label_name[-2:]
            self._add_label_name(label_name, hemi)

    def _set_annotations(self, parcellation):
        fsmri = self.paramdlg._fsmri
        self.parcellation = parcellation
        self.clear_glyphs()
        self.remove_labels()
        self.remove_annotations()
        labels = fsmri.get_labels(parcellation=parcellation)
        if parcellation == "Other":
            for label in labels:
                self.add_label(label, borders=True, color="k", alpha=0.75)
        else:
            self.add_annotation(
                parcellation, borders=True, color="k", alpha=0.75, remove_existing=True
            )

        # Add label coordinates to dictionary to allow selection
        for hemi in self._hemis:
            hemi_labels = [lb for lb in labels if lb.hemi == hemi]
            self._vertex_to_label_id[hemi] = np.full(self.geo[hemi].coords.shape[0], -1)
            self._annotation_labels[hemi] = hemi_labels
            for idx, hemi_label in enumerate(hemi_labels):
                self._vertex_to_label_id[hemi][hemi_label.vertices] = idx

        # Update text
        self._actors["text"]["title"].SetInput(
            f"Subject={self.paramdlg._fsmri.name}, Parcellation={parcellation}\n"
            f"Select labels by clicking on them"
        )

    def _init_picking(self):
        self._mouse_no_mvt = -1
        add_obs = self._renderer.plotter.iren.add_observer
        add_obs(vtkCommand.RenderEvent, self._on_mouse_move)
        add_obs(vtkCommand.LeftButtonPressEvent, self._on_button_press)
        add_obs(vtkCommand.EndInteractionEvent, self._on_button_release)
        self._renderer.plotter.picker = vtkCellPicker()
        self._renderer.plotter.picker.AddObserver(
            vtkCommand.EndPickEvent, self._label_picked
        )

    def _label_picked(self, vtk_picker, _):
        cell_id = vtk_picker.GetCellId()
        mesh = vtk_picker.GetDataSet()
        if mesh is not None:
            hemi = mesh._hemi
            if mesh is None or cell_id == -1 or not self._mouse_no_mvt:
                return  # don't pick
            pos = np.array(vtk_picker.GetPickPosition())
            vtk_cell = mesh.GetCell(cell_id)
            cell = [
                vtk_cell.GetPointId(point_id)
                for point_id in range(vtk_cell.GetNumberOfPoints())
            ]
            vertices = mesh.points[cell]
            idx = np.argmin(abs(vertices - pos), axis=0)
            vertex_id = cell[idx[0]]

            label_id = self._vertex_to_label_id[hemi][vertex_id]
            label = self._annotation_labels[hemi][label_id]

            if label.name in self.selected:
                self._remove_label_name(label.name, hemi)
                self.selected.remove(label.name)
            else:
                self._add_label_name(label.name, hemi, label)
                self.selected.append(label.name)
            self.list_changed_slot()
            self.paramdlg.update_selected_display()

            # Update label text
            if "label" in self._actors["text"]:
                self.remove_text("label")
            if label.color is not None:
                color = label.color[:3]
                opacity = label.color[-1]
            else:
                color = "w"
                opacity = 1
            self.add_text(
                0,
                0.05,
                label.name,
                color=color,
                opacity=opacity,
                font_size=12,
                name="label",
            )

    def _add_label_name(self, label_name, hemi, label=None):
        if label is None:
            for lb in self._annotation_labels[hemi]:
                if lb.name == label_name:
                    label = lb
                    break
        if label is not None:
            self.add_label(label, borders=False)
            self._shown_labels.append(label_name)

    def _remove_label_name(self, label_name, hemi):
        self._layered_meshes[hemi].remove_overlay(label_name)
        self._shown_labels.remove(label_name)
        self._renderer._update()

    def isclosed(self):
        if self.plotter is None:
            self._closed = True
        return self._closed

    def close(self):
        if self.plotter is not None:
            super().close()
        self._closed = True


class LabelDialog(SimpleDialog):
    def __init__(self, paramw):
        self.main_widget = QWidget()
        super().__init__(
            self.main_widget,
            parent=paramw,
            title="Choose a label!",
            window_title="Label Picker",
            modal=False,
        )
        self.paramw = paramw
        self.ct = paramw.data

        self._parc_picker = None
        self._extra_picker = None
        self._fsmri = None
        self._parcellation = None
        self._surface = None
        # Put selected labels from LabelGui in both parc and extra,
        # since they get removed if not fitting later anyway
        self._parc_labels = []
        self._selected_parc_labels = copy(paramw.value) or []
        self._extra_labels = []
        self._selected_extra_labels = copy(paramw.value) or []

        self.resize(400, 800)
        center(self)

        self._init_layout()

        # Initialize with first items
        self._subject_changed()
        self._surface_changed()

        self.open()

    def _init_layout(self):
        layout = QVBoxLayout(self.main_widget)

        layout.addWidget(QLabel("Choose a subject:"))
        self.fsmri_cmbx = QComboBox()
        self.fsmri_cmbx.addItems(self.ct.pr.all_fsmri)
        self.fsmri_cmbx.activated.connect(self._subject_changed)
        layout.addWidget(self.fsmri_cmbx)

        layout.addWidget(QLabel("Choose a parcellation:"))
        self.parcellation_cmbx = QComboBox()
        self.parcellation_cmbx.activated.connect(self._parc_changed)
        layout.addWidget(self.parcellation_cmbx)

        layout.addWidget(QLabel("Choose a surface:"))
        self.surface_cmbx = QComboBox()
        self.surface_cmbx.addItems(["inflated", "pial", "white"])
        self.surface_cmbx.activated.connect(self._surface_changed)
        layout.addWidget(self.surface_cmbx)

        self.selected_display = SimpleList(
            data=self._selected_parc_labels + self._selected_extra_labels,
            title="Selected Labels",
        )
        layout.addWidget(self.selected_display)

        self.parc_label_list = CheckList(
            data=self._parc_labels,
            checked=self._selected_parc_labels,
            ui_buttons=True,
            ui_button_pos="bottom",
            title="Parcellation Labels",
        )
        self.parc_label_list.checkedChanged.connect(
            partial(self._labels_changed, picker_name="parcellation")
        )
        layout.addWidget(self.parc_label_list)

        self.extra_label_list = CheckList(
            data=self._extra_labels,
            checked=self._selected_extra_labels,
            ui_buttons=True,
            ui_button_pos="bottom",
            title="Extra Labels",
        )
        self.extra_label_list.checkedChanged.connect(
            partial(self._labels_changed, picker_name="extra")
        )
        layout.addWidget(self.extra_label_list)

        self.choose_parc_bt = QPushButton("Choose Parcellation Labels")
        self.choose_parc_bt.clicked.connect(self._open_parc_picker)
        layout.addWidget(self.choose_parc_bt)

        self.choose_extra_bt = QPushButton("Choose Extra Labels")
        self.choose_extra_bt.clicked.connect(self._open_extra_picker)
        layout.addWidget(self.choose_extra_bt)

    def _subject_changed(self):
        self._fsmri = FSMRI(self.fsmri_cmbx.currentText(), self.ct, load_labels=True)

        self.parcellation_cmbx.clear()
        self.parcellation_cmbx.addItems(self._fsmri.parcellations)

        # Update extra labels
        self._extra_labels.clear()
        self._extra_labels += [lb.name for lb in self._fsmri.labels["Other"]]
        self.extra_label_list.content_changed()

        old_selected_extra = self._selected_extra_labels.copy()
        self._selected_extra_labels.clear()
        self._selected_extra_labels += [
            lb for lb in old_selected_extra if lb in self._extra_labels
        ]
        self.extra_label_list.content_changed()

        # Update selected parcellation labels
        all_labels_exept_other = []
        for parc_name, labels in self._fsmri.labels.items():
            if parc_name != "Other":
                all_labels_exept_other += [lb.name for lb in labels]
        old_selected_parc = self._selected_parc_labels.copy()
        self._selected_parc_labels.clear()
        self._selected_parc_labels += [
            lb for lb in old_selected_parc if lb in all_labels_exept_other
        ]

        # Update pickers if open
        if self._parc_picker is not None and not self._parc_picker.isclosed():
            self._parc_picker.close()
            self._open_parc_picker()
        if self._extra_picker is not None and not self._extra_picker.isclosed():
            self._extra_picker.close()
            self._open_extra_picker()

        # Update parcellation labels
        self._parc_changed()

    def _parc_changed(self):
        # Keep reference for inplace change
        self._parc_labels.clear()

        # Add parcellation labels
        self._parcellation = self.parcellation_cmbx.currentText()
        if self._parcellation in self._fsmri.labels:
            self._parc_labels += [
                lb.name for lb in self._fsmri.labels[self._parcellation]
            ]

        self.parc_label_list.content_changed()

        if self._parc_picker is not None and not self._parc_picker.isclosed():
            self._parc_picker._set_annotations(self._parcellation)
            for label_name in [
                lb for lb in self._selected_parc_labels if lb in self._parc_labels
            ]:
                hemi = label_name[-2:]
                self._parc_picker._add_label_name(label_name, hemi)

    def _surface_changed(self):
        self._surface = self.surface_cmbx.currentText()
        if self._parc_picker is not None and not self._parc_picker.isclosed():
            self._parc_picker.close()
            self._open_parc_picker()

    def update_selected_display(self):
        self.selected_display.replace_data(
            self._selected_parc_labels + self._selected_extra_labels
        )

    def _labels_changed(self, labels, picker_name):
        picker = (
            self._parc_picker if picker_name == "parcellation" else self._extra_picker
        )
        if picker is not None:
            shown_labels = picker._shown_labels
            for add_name in [lb for lb in labels if lb not in shown_labels]:
                hemi = add_name[-2:]
                picker._add_label_name(add_name, hemi)
            for remove_name in [lb for lb in shown_labels if lb not in labels]:
                hemi = remove_name[-2:]
                picker._remove_label_name(remove_name, hemi)
        # Update display
        self.update_selected_display()

    # Keep pickers on top
    def _open_parc_picker(self):
        self._parc_picker = LabelPicker(
            self,
            self._parcellation,
            self._surface,
            self._selected_parc_labels,
            self.parc_label_list.content_changed,
            title="Pick parcellation labels",
        )

    def _open_extra_picker(self):
        self._extra_picker = LabelPicker(
            self,
            "Other",
            self._surface,
            self._selected_extra_labels,
            self.extra_label_list.content_changed,
            title="Pick extra labels",
        )

    def closeEvent(self, event):
        self.paramw.set_param(self._selected_parc_labels + self._selected_extra_labels)
        for picker in [self._parc_picker, self._extra_picker]:
            if picker is not None and not picker.isclosed():
                picker.close()
        self.hide()


class LabelGui(Param):
    """This GUI lets the user pick labels from a brain."""

    data_type = list

    def __init__(self, value_string_length=30, **kwargs):
        """
        Parameters
        ----------
        value_string_length : int | None
            Set the limit of characters to which the value converted to a
            string will be displayed.
        **kwargs
            All the parameters fo :method:`~Param.__init__` go here.
        """

        super().__init__(**kwargs)
        self.value_string_length = value_string_length
        if not isinstance(self.data, Controller):
            raise RuntimeError(
                "LabelGui can only used with an instance of Controller passed as data."
            )
        self._dialog = None
        self.cached_value = None
        check_list_layout = QHBoxLayout()
        self.value_label = QLabel()
        check_list_layout.addWidget(self.value_label)
        self.param_widget = QPushButton("Edit")
        self.param_widget.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
        self.param_widget.clicked.connect(self.show_dialog)
        check_list_layout.addWidget(self.param_widget)

        self.init_ui(check_list_layout)

    def show_dialog(self):
        if self._dialog is None:
            self._dialog = LabelDialog(self)
        else:
            self._dialog.show()

    def _set_widget_value(self, value):
        if value is not None:
            self.cached_value = value
        self.value_label.setText(
            convert_list_to_string(value, self.param_unit, self.value_string_length)
        )

    def _get_widget_value(self):
        if self.value is None:
            if self.cached_value:
                value = self.cached_value
            else:
                value = []
            self.value_label.clear()
        else:
            value = self.value

        return value


class ColorGui(Param):
    """A GUI to pick a color and returns a dictionary with HexRGBA-Strings."""

    data_type = dict

    def __init__(self, keys, **kwargs):
        """
        Parameters
        ----------
        keys : dict | str | None
            If you supply a dictionary with keys, you can set a color
            for each key. If you supply the string name of another parameter
            (which must return an iterable!), the values from there are taken.
        **kwargs
            All the parameters for :method:`Param.__init__` go here.
        """

        super().__init__(**kwargs)

        if isinstance(keys, str):
            self.keys = self._load_from_data(keys)
        else:
            self.keys = keys
        self._cached_value = None
        layout = QHBoxLayout()
        self.select_widget = QComboBox()
        self.select_widget.setEditable(True)
        self.select_widget.addItems([str(k) for k in self.keys])
        self.select_widget.activated.connect(self._change_display_color)
        layout.addWidget(self.select_widget)
        self.display_widget = QLabel()
        self.display_widget.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        layout.addWidget(self.display_widget)
        self.param_widget = QPushButton("Pick Color")
        self.param_widget.clicked.connect(self._pick_color)
        layout.addWidget(self.param_widget)
        self.init_ui(layout)

    def _change_display_color(self):
        key = self.select_widget.currentText()
        if key in self._cached_value:
            color = _get_color(self._cached_value[key])
            pixmap = QPixmap(20, 20)
            pixmap.fill(color)
            self.display_widget.setPixmap(pixmap)
        else:
            self.display_widget.setText("None")

    def _set_widget_value(self, value):
        self._cached_value = value
        self.keys = value.keys()
        self._change_display_color()

    def _get_widget_value(self):
        return self._cached_value

    def _pick_color(self):
        key = self.select_widget.currentText()
        if key in self._cached_value:
            previous_color = _get_color(self._cached_value[key])
            color = QColorDialog.getColor(
                initial=previous_color,
                parent=self,
                title=f"Pick a color for {self.name}",
            )
        else:
            # blocking
            color = QColorDialog.getColor(
                parent=self, title=f"Pick a color for {self.name}"
            )
        self._cached_value[key] = color.name()
        self.value = self._cached_value


class PathGui(Param):
    """A GUI to pick a path."""

    data_type = Path

    def __init__(self, pick_mode="file", **kwargs):
        """
        Parameters
        ----------
        pick_mode : str
            Can be either "file" or "directory".
        **kwargs
            All the parameters for :method:`Param.__init__` go here.
        """

        super().__init__(**kwargs)

        self.pick_mode = pick_mode
        self._path = None
        layout = QHBoxLayout()
        self.display_widget = QLabel()
        layout.addWidget(self.display_widget)
        self.param_widget = QPushButton("Pick Path")
        self.param_widget.clicked.connect(self._pick_path)
        layout.addWidget(self.param_widget)
        self.init_ui(layout)

    def _pick_path(self):
        if self.pick_mode == "file":
            self._path = compat.getopenfilename(self, self.description)[0]
        else:
            self._path = compat.getexistingdirectory(self, self.description)
        self.value = self._path

    def _set_widget_value(self, value):
        self._path = value
        self.display_widget.setText(str(value))

    def _get_widget_value(self):
        return self._path


# Todo: Ordering Parameters in Tabs and add Find-Command
class ResetDialog(QDialog):
    def __init__(self, p_dock):
        super().__init__(p_dock)
        self.pd = p_dock
        self.selected_params = []

        self.init_ui()
        self.open()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.addWidget(
            CheckList(
                list(self.pd.ct.pr.parameters[self.pd.ct.pr.p_preset].keys()),
                self.selected_params,
                title="Select the Parameters to reset",
            )
        )
        reset_bt = QPushButton("Reset")
        reset_bt.clicked.connect(self.reset_params)
        layout.addWidget(reset_bt)

        close_bt = QPushButton("Close")
        close_bt.clicked.connect(self.close)
        layout.addWidget(close_bt)

        self.setLayout(layout)

    def reset_params(self):
        for name in self.selected_params:
            self.pd.ct.pr.load_default_param(name)
            print(f"Reset {name}")
        WorkerDialog(self, self.pd.ct.pr.save, title="Saving project...", blocking=True)
        self.pd.update_all_param_guis()
        self.close()


class CopyPDialog(QDialog):
    def __init__(self, p_dock):
        super().__init__(p_dock)
        self.pd = p_dock
        self.p = p_dock.ct.pr.parameters
        self.selected_from = None
        self.selected_to = []
        self.selected_ps = []

        self.init_ui()
        self.open()

    def init_ui(self):
        layout = QVBoxLayout()

        list_layout = QHBoxLayout()
        copy_from = SimpleList(list(self.p.keys()))
        copy_from.currentChanged.connect(self.from_selected)
        list_layout.addWidget(copy_from)

        self.copy_to = CheckList(checked=self.selected_to)
        list_layout.addWidget(self.copy_to)

        self.copy_ps = CheckList(checked=self.selected_ps)
        list_layout.addWidget(self.copy_ps)

        layout.addLayout(list_layout)

        bt_layout = QHBoxLayout()

        copy_bt = QPushButton("Copy")
        copy_bt.clicked.connect(self.copy_parameters)
        bt_layout.addWidget(copy_bt)

        close_bt = QPushButton("Close")
        close_bt.clicked.connect(self.close)
        bt_layout.addWidget(close_bt)

        layout.addLayout(bt_layout)

        self.setLayout(layout)

    def from_selected(self, current):
        self.selected_from = current
        self.copy_to.replace_data([pp for pp in self.p.keys() if pp != current])
        self.copy_ps.replace_data([p for p in self.p[current]])

    def copy_parameters(self):
        if len(self.selected_to) > 0:
            for p_preset in self.selected_to:
                for parameter in self.selected_ps:
                    self.p[p_preset][parameter] = self.p[self.selected_from][parameter]

            WorkerDialog(
                self, self.pd.ct.pr.save, title="Saving project...", blocking=True
            )
            self.pd.update_all_param_guis()
            self.close()


class RemovePPresetDlg(CheckListDlg):
    def __init__(self, parent):
        self.parent = parent
        self.preset_list = [p for p in self.parent.ct.pr.parameters if p != "Default"]
        self.rm_list = []

        super().__init__(parent, self.preset_list, self.rm_list)

        self.do_bt.setText("Remove Parameter-Preset")
        self.do_bt.clicked.connect(self.remove_selected)

        self.open()

    def remove_selected(self):
        for p_preset in self.rm_list:
            self.preset_list.remove(p_preset)
            self.lm.layoutChanged.emit()
            # Remove from Parameters
            self.parent.ct.pr.parameters.pop(p_preset)
            self.parent.update_ppreset_cmbx()

        # If current Parameter-Preset was deleted
        if self.parent.ct.pr.p_preset not in self.parent.ct.pr.parameters:
            self.parent.ct.pr.p_preset = list(self.parent.ct.pr.parameters.keys())[0]
            self.parent.update_all_param_guis()

        self.close()


class ParametersDock(QDockWidget):
    def __init__(self, main_win):
        super().__init__("Parameters", main_win)
        self.mw = main_win
        self.ct = main_win.ct
        self.setAllowedAreas(Qt.RightDockWidgetArea)
        self.main_widget = QWidget()
        self.param_guis = {}

        self.dropgroup_params()
        self.init_ui()

    def dropgroup_params(self):
        # Create a set of all unique parameters used by functions
        # in selected_modules
        sel_pdfuncs = self.ct.pd_funcs.loc[
            self.ct.pd_funcs["module"].isin(self.ct.get_setting("selected_modules"))
        ]
        # Remove rows with NaN in func_args
        sel_pdfuncs = sel_pdfuncs.loc[sel_pdfuncs["func_args"].notna()]
        all_used_params_str = ",".join(sel_pdfuncs["func_args"])
        # Make sure there are no spaces left
        all_used_params_str = all_used_params_str.replace(" ", "")
        all_used_params = set(all_used_params_str.split(","))
        drop_idx_list = []
        self.cleaned_pd_params = self.ct.pd_params.copy()
        for param in self.cleaned_pd_params.index:
            if param in all_used_params:
                # Group-Name (if not given, set to 'Various')
                group_name = self.cleaned_pd_params.loc[param, "group"]
                if pd.isna(group_name):
                    self.cleaned_pd_params.loc[param, "group"] = "Various"
            else:
                # Drop Parameters which aren't used by functions
                drop_idx_list.append(param)
        self.cleaned_pd_params.drop(index=drop_idx_list, inplace=True)

    def init_ui(self):
        self.general_layout = QVBoxLayout()

        # Add Parameter-Preset-ComboBox
        title_layouts = QVBoxLayout()
        title_layout1 = QHBoxLayout()
        p_preset_l = QLabel("Parameter-Presets: ")
        title_layout1.addWidget(p_preset_l)
        self.p_preset_cmbx = QComboBox()
        self.p_preset_cmbx.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.p_preset_cmbx.activated.connect(self.p_preset_changed)
        self.update_ppreset_cmbx()
        title_layout1.addWidget(self.p_preset_cmbx)

        add_bt = QPushButton(icon=get_std_icon("SP_FileDialogNewFolder"))
        add_bt.clicked.connect(self.add_p_preset)
        title_layout1.addWidget(add_bt)

        rm_bt = QPushButton(icon=get_std_icon("SP_DialogDiscardButton"))
        rm_bt.clicked.connect(partial(RemovePPresetDlg, self))
        title_layout1.addWidget(rm_bt)

        title_layouts.addLayout(title_layout1)

        title_layout2 = QHBoxLayout()
        copy_bt = QPushButton("Copy")
        copy_bt.setFont(QFont(Settings().value("app_font"), 16))
        copy_bt.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
        copy_bt.clicked.connect(partial(CopyPDialog, self))
        title_layout2.addWidget(copy_bt)

        reset_bt = QPushButton("Reset")
        reset_bt.setFont(QFont(Settings().value("app_font"), 16))
        reset_bt.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
        reset_bt.clicked.connect(partial(ResetDialog, self))
        title_layout2.addWidget(reset_bt)

        reset_all_bt = QPushButton("Reset All")
        reset_all_bt.setFont(QFont(Settings().value("app_font"), 16))
        reset_all_bt.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
        reset_all_bt.clicked.connect(self.reset_all_parameters)
        title_layout2.addWidget(reset_all_bt)

        title_layouts.addLayout(title_layout2)
        self.general_layout.addLayout(title_layouts)

        self.add_param_guis()

        self.main_widget.setLayout(self.general_layout)
        self.setWidget(self.main_widget)

    def add_param_guis(self):
        # Create Tab-Widget for Parameters, grouped by group
        self.tab_param_widget = QTabWidget()

        grouped_params = self.cleaned_pd_params.groupby("group", sort=False)

        for group_name, group in grouped_params:
            layout = QVBoxLayout()
            tab = QScrollArea()
            child_w = QWidget()
            for idx, parameter in group.iterrows():
                # Get Parameters for Gui-Call
                if pd.notna(parameter["alias"]):
                    alias = parameter["alias"]
                else:
                    alias = idx
                if pd.notna(parameter["gui_type"]):
                    gui_name = parameter["gui_type"]
                else:
                    gui_name = "FuncGui"
                try:
                    default = literal_eval(parameter["default"])
                except (SyntaxError, ValueError):
                    if gui_name == "FuncGui":
                        default = _eval_param(parameter["default"])
                    else:
                        default = parameter["default"]
                if pd.notna(parameter["description"]):
                    description = parameter["description"]
                else:
                    description = ""
                if pd.notna(parameter["unit"]):
                    unit = parameter["unit"]
                else:
                    unit = None
                try:
                    gui_args = literal_eval(parameter["gui_args"])
                except (SyntaxError, ValueError):
                    gui_args = {}

                try:
                    self.param_guis[idx] = globals()[gui_name](
                        data=self.ct,
                        name=idx,
                        alias=alias,
                        default=default,
                        description=description,
                        param_unit=unit,
                        **gui_args,
                    )
                except Exception:
                    err_tuple = get_exception_tuple()
                    raise RuntimeError(
                        f'Initialization of Parameter-Widget "{idx}" '
                        f"with value={default} "
                        f"failed:\n"
                        f"{err_tuple[1]}"
                    )

                layout.addWidget(self.param_guis[idx])

            child_w.setLayout(layout)
            tab.setWidget(child_w)
            self.tab_param_widget.addTab(tab, group_name)

        # Set Layout of QWidget (the class itself)
        self.general_layout.addWidget(self.tab_param_widget)

    def update_ppreset_cmbx(self):
        self.p_preset_cmbx.clear()
        for p_preset in self.ct.pr.parameters.keys():
            self.p_preset_cmbx.addItem(p_preset)
        if self.ct.pr.p_preset in self.ct.pr.parameters.keys():
            self.p_preset_cmbx.setCurrentText(self.ct.pr.p_preset)
        else:
            self.p_preset_cmbx.setCurrentText(list(self.ct.pr.parameters.keys())[0])

    def p_preset_changed(self, idx):
        self.ct.pr.p_preset = self.p_preset_cmbx.itemText(idx)
        self.update_all_param_guis()

    def add_p_preset(self):
        preset_name = get_user_input(
            "Enter a name for a new Parameter-Preset:", "string"
        )
        if preset_name is not None:
            self.ct.pr.p_preset = preset_name
            self.ct.pr.load_default_parameters()
            self.p_preset_cmbx.addItem(preset_name)
            self.p_preset_cmbx.setCurrentText(preset_name)

    def redraw_param_widgets(self):
        self.general_layout.removeWidget(self.tab_param_widget)
        self.tab_param_widget.close()
        del self.tab_param_widget
        self.dropgroup_params()
        self.add_param_guis()
        self.update_ppreset_cmbx()

    def update_all_param_guis(self):
        for gui_name in self.param_guis:
            param_gui = self.param_guis[gui_name]
            param_gui.read_param()
            param_gui._set_param()

    def reset_all_parameters(self):
        msgbox = QMessageBox.question(
            self,
            "Reset all Parameters?",
            "Do you really want to reset all parameters to their default?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if msgbox == QMessageBox.Yes:
            self.ct.pr.load_default_parameters()
            self.update_all_param_guis()


class SettingsDlg(QDialog):
    def __init__(self, parent_widget, controller):
        super().__init__(parent_widget)
        self.ct = controller

        self.settings_items = {
            "app_theme": {
                "gui_type": "ComboGui",
                "data_type": "QSettings",
                "slot": set_app_theme,
                "gui_kwargs": {
                    "alias": "Application Theme",
                    "description": "Changes the application theme (Restart required).",
                    "options": ["auto", "light", "dark", "high_contrast"],
                    "raise_missing": False,
                },
            },
            "app_font": {
                "gui_type": "ComboGui",
                "data_type": "QSettings",
                "slot": set_app_font,
                "gui_kwargs": {
                    "alias": "Application Font",
                    "description": "Changes default application font "
                    "(Restart required).",
                    "options": QFontDatabase.families(QFontDatabase.Latin),
                    "raise_missing": False,
                },
            },
            "app_font_size": {
                "gui_type": "IntGui",
                "data_type": "QSettings",
                "slot": set_app_font,
                "gui_kwargs": {
                    "alias": "Font Size",
                    "description": "Changes default application font-size "
                    "(Restart required).",
                    "min_val": 5,
                    "max_val": 20,
                },
            },
            "img_format": {
                "gui_type": "ComboGui",
                "data_type": "Settings",
                "gui_kwargs": {
                    "alias": "Image Format",
                    "description": "Choose the image format for plots.",
                    "options": [".png", ".jpg", ".tiff"],
                },
            },
            "dpi": {
                "gui_type": "IntGui",
                "data_type": "Settings",
                "gui_kwargs": {
                    "alias": "DPI",
                    "description": "Set dpi for saved plots.",
                    "min_val": 10,
                    "max_val": 5000,
                },
            },
            "enable_cuda": {
                "gui_type": "BoolGui",
                "data_type": "QSettings",
                "gui_kwargs": {
                    "alias": "Enable CUDA",
                    "description": "Enable for CUDA support "
                    "(system has to be setup for cuda "
                    "as in https://mne.tools/stable/install/"
                    "advanced.html#gpu-acceleration-with-cuda)",
                    "return_integer": True,
                },
            },
            "save_ram": {
                "gui_type": "BoolGui",
                "data_type": "QSettings",
                "gui_kwargs": {
                    "alias": "Save RAM",
                    "description": "Set to True on low RAM-Machines to avoid"
                    " the process to be killed by the OS due "
                    "to low Memory (with leaving it off, "
                    "the pipeline goes a bit faster, because "
                    "the data can be saved in memory).",
                    "return_integer": True,
                },
            },
            "fs_path": {
                "gui_type": "StringGui",
                "data_type": "QSettings",
                "gui_kwargs": {
                    "alias": "FREESURFER_HOME-Path",
                    "description": 'Set the Path to the "freesurfer"-directory'
                    " of your Freesurfer-Installation "
                    "(for Windows to the LINUX-Path of the "
                    "Freesurfer-Installation in "
                    "Windows-Subsystem for Linux(WSL))",
                    "none_select": True,
                },
            },
            "mne_path": {
                "gui_type": "StringGui",
                "data_type": "QSettings",
                "gui_kwargs": {
                    "alias": "MNE-WSL-Path",
                    "description": "Set the LINUX-Path to the mne-environment "
                    "(e.g ...anaconda3/envs/mne) in "
                    "Windows-Subsystem for Linux(WSL))",
                    "none_select": True,
                },
            },
        }

        if not iswin:
            self.settings_items.pop("mne_path")

        self.init_ui()
        self.open()

    def init_ui(self):
        layout = QVBoxLayout()

        for setting, details in self.settings_items.items():
            gui_handle = globals()[details["gui_type"]]
            data_type = details["data_type"]
            gui_kwargs = details["gui_kwargs"]
            if data_type == "QSettings":
                gui_kwargs["data"] = Settings()
                gui_kwargs["default"] = self.ct.default_settings["qsettings"][setting]
            elif data_type == "Controller":
                gui_kwargs["data"] = self.mw.ct
                gui_kwargs["default"] = self.ct.pd_params.loc[setting, "default"]
            else:
                gui_kwargs["data"] = self.ct.settings
                gui_kwargs["default"] = self.ct.default_settings["settings"][setting]
            gui_kwargs["name"] = setting
            gui = gui_handle(**gui_kwargs)
            if details.get("slot"):
                gui.paramChanged.connect(details["slot"])
            layout.addWidget(gui)
        close_bt = QPushButton("Close")
        close_bt.clicked.connect(self.close)
        layout.addWidget(close_bt)

        self.setLayout(layout)
