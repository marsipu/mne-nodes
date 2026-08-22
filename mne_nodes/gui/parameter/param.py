"""Base parameter GUI class."""

from __future__ import annotations

from collections.abc import MutableMapping
from types import NoneType
from typing import Any

from qtpy.QtCore import Qt, Signal
from qtpy.QtWidgets import QCheckBox, QGroupBox, QHBoxLayout, QLabel, QWidget

from mne_nodes.logger import logger
from mne_nodes.pipeline.controller import Controller
from mne_nodes.pipeline.settings import Settings


class Param(QWidget):
    """Base-Class Parameter-GUIs.

    Parameters
    ----------
    data : MutableMapping[str, Any] | Controller | Settings
        The data source the parameter value is loaded from and saved to.
    name : str
        The key under which the value is stored in *data*.
    function_name : str | None
        Name of the function the parameter belongs to. Required when *data*
        is a :class:`~mne_nodes.pipeline.controller.Controller`.
    alias : str | None
        Display name shown in the GUI. Defaults to *name*.
    default : object | None
        Value used when *name* is not present in *data* or has the wrong type.
    unit : str | None
        Unit label displayed alongside the value.
    groupbox_layout : bool
        If ``True``, wrap the widget in a checkable :class:`~qtpy.QtWidgets.QGroupBox`
        (used for none-selection). If ``False``, use a plain label/checkbox layout.
    none_select : bool
        If ``True``, allow the value to be set to ``None`` via a checkbox or groupbox.
    show_title : bool
        Whether to display *alias* as a title/label.
    description : str | None
        Tooltip text shown for the widget.
    parent_widget : QWidget | None
        Parent widget passed to :class:`~qtpy.QtWidgets.QWidget`.
    """

    data_type = object
    paramChanged = Signal(object)

    def __init__(
        self,
        data: MutableMapping[str, Any] | Controller | Settings,
        name: str,
        function_name: str | None = None,
        alias: str | None = None,
        default: object | None = None,
        unit: str | None = None,
        groupbox_layout: bool = True,
        none_select: bool = False,
        show_title: bool = True,
        description: str | None = None,
        parent_widget: QWidget | None = None,
        *args: Any,
        **kwargs: Any,
    ):
        """Initialize the parameter GUI and load its value from *data*."""
        super().__init__(*args, parent=parent_widget, **kwargs)
        if isinstance(data, Controller) and function_name is None:
            raise RuntimeError(
                "Function name must be provided when using Controller as data source."
            )
        self.data = data
        self.name = name
        self.function_name = function_name
        self.alias = alias if alias else self.name
        self._value = None
        self._previous_value = None
        self.default = default
        self.unit = unit
        self.groupbox_layout = groupbox_layout
        self.none_select = none_select
        self.show_title = show_title
        self.description = description
        if description is not None:
            self.setToolTip(description)
        self.group_box = None
        self.none_chkbx = None
        self.param_layout = None

        self._value = self._load_from_data(self.name)
        if self._value is not None:
            self._previous_value = self._value

    def read_param(self):
        """Reload the current value from the data source."""
        self._value = self._load_from_data(self.name)

    def set_param(self, value):
        """Set the parameter value (equivalent to assigning to :attr:`value`)."""
        self.value = value

    def _set_param(self):
        """Push the current value through the update pipeline without changing it."""
        self._update_param()

    @property
    def value(self):
        """Return the current parameter value."""
        return self._value

    @value.setter
    def value(self, new_value):
        """Set the parameter value, updating the GUI and persisting it to data."""
        self._value = new_value
        if new_value is not None:
            self._previous_value = new_value
        self._update_param()

    def _update_param(self):
        """Refresh the widget, persist the value and emit :attr:`paramChanged`."""
        self._update_gui()
        self._save_to_data(self.name, self._value)
        self.paramChanged.emit(self._value)

    def _update_gui(self):
        """Sync the none-checkbox/groupbox state and widget value with :attr:`value`."""
        self._check_none_state()
        if self._value is not None:
            self._set_widget_value(self._value)

    def _on_widget_changed(self):
        """Handle changes originating from the underlying widget."""
        if self.none_select and not self._is_enabled():
            self.value = None
        else:
            widget_value = self._get_widget_value()
            if widget_value != self._value:
                self.value = widget_value

    def _on_none_changed(self, checked=None):
        """Handle toggling of the none-checkbox/groupbox."""
        if checked == Qt.CheckState.Checked or checked is True:
            self._set_enabled(True)
            if self._value is None:
                restored_value = self._previous_value
                if restored_value is None:
                    restored_value = self._get_widget_value()
                self.value = restored_value
        else:
            self.value = None
            self._set_enabled(False)

    def _set_enabled(self, enabled):
        """Enable or disable the parameter widget(s) (non-groupbox layout only)."""
        if not self.groupbox_layout and self.param_layout is not None:
            for i in range(self.param_layout.count()):
                widget = self.param_layout.itemAt(i).widget()
                if widget is not None:
                    widget.setEnabled(enabled)

    def _is_enabled(self):
        """Return whether the parameter widget is currently enabled."""
        if self.groupbox_layout and self.group_box:
            return self.group_box.isChecked()
        if self.none_chkbx:
            return self.none_chkbx.isChecked()
        return True

    def _check_none_state(self):
        """Sync the none-checkbox/groupbox checked state with :attr:`value`."""
        if self.none_select:
            checked = self._value is not None
            if self.groupbox_layout:
                self.group_box.setChecked(checked)
            else:
                self.none_chkbx.setChecked(checked)
                self._set_enabled(checked)

    def _load_from_data(self, name):
        """Load and validate the value stored under *name* in the data source."""
        if isinstance(self.data, Controller):
            value = self.data.parameter(name, function_name=self.function_name)
        elif isinstance(self.data, dict):
            value = self.data.get(name, self.default)
        elif isinstance(self.data, Settings) and name in self.data:
            value = self.data.get(name)
        else:
            logger.warning(
                f"Parameter {name} not found in data source, using default value."
            )
            value = self.default

        dt = self.data_type
        if self.none_select:
            dt = dt | NoneType
        if not isinstance(value, dt):
            logger.warning(
                f"Data for {name} has to be of type {dt}, "
                f"but is of type {type(value)} instead!\n"
                f"Using default value {self.default} instead."
            )
            value = self.default
        return value

    def _save_to_data(self, name, value):
        """Persist *value* under *name* in the data source."""
        if isinstance(self.data, Controller):
            self.data.set_parameter(name, value, function_name=self.function_name)
        elif isinstance(self.data, dict):
            self.data[name] = value
        elif isinstance(self.data, Settings):
            self.data.set(name, value)

    def is_key(self, key):
        """Return whether *key* exists in the data source."""
        if isinstance(self.data, Controller):
            return key in self.data.get("parameters")[self.function_name]
        if isinstance(self.data, dict):
            return key in self.data
        if isinstance(self.data, Settings):
            return key in self.data
        return False

    def _get_widget_value(self) -> Any:
        """Return the value currently displayed by the widget (subclass hook)."""

    def _set_widget_value(self, value):
        """Display *value* in the widget (subclass hook)."""

    def init_ui(self, layout):
        """Build the surrounding groupbox/checkbox/label layout around *layout*."""
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
                self.none_chkbx = QCheckBox(self.alias if self.show_title else "")
                self.none_chkbx.checkStateChanged.connect(self._on_none_changed)
                main_layout.addWidget(self.none_chkbx)
            elif self.show_title:
                name_label = QLabel(self.alias)
                main_layout.addWidget(name_label)
            main_layout.addLayout(layout)

        self.setLayout(main_layout)
        self._update_gui()
