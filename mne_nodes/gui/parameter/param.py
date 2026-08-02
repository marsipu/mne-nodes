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
    """Base-Class Parameter-GUIs."""

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
        description: str | None = None,
        parent_widget: QWidget | None = None,
        *args: Any,
        **kwargs: Any,
    ):
        super().__init__(parent=parent_widget, *args, **kwargs)
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
        self._value = self._load_from_data(self.name)

    def set_param(self, value):
        self.value = value

    def _set_param(self):
        self._update_param()

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, new_value):
        self._value = new_value
        if new_value is not None:
            self._previous_value = new_value
        self._update_param()

    def _update_param(self):
        self._update_gui()
        self._save_to_data(self.name, self._value)
        self.paramChanged.emit(self._value)

    def _update_gui(self):
        self._check_none_state()
        if self._value is not None:
            self._set_widget_value(self._value)

    def _on_widget_changed(self):
        if self.none_select and not self._is_enabled():
            self.value = None
        else:
            widget_value = self._get_widget_value()
            if widget_value != self._value:
                self.value = widget_value

    def _on_none_changed(self, checked=None):
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
        if not self.groupbox_layout and self.param_layout is not None:
            for i in range(self.param_layout.count()):
                widget = self.param_layout.itemAt(i).widget()
                if widget is not None:
                    widget.setEnabled(enabled)

    def _is_enabled(self):
        if self.groupbox_layout and self.group_box:
            return self.group_box.isChecked()
        if self.none_chkbx:
            return self.none_chkbx.isChecked()
        return True

    def _check_none_state(self):
        if self.none_select:
            checked = self._value is not None
            if self.groupbox_layout:
                self.group_box.setChecked(checked)
            else:
                self.none_chkbx.setChecked(checked)
                self._set_enabled(checked)

    def _load_from_data(self, name):
        if isinstance(self.data, Controller):
            value = self.data.parameter(name, function_name=self.function_name)
        elif isinstance(self.data, dict):
            value = self.data.get(name, self.default)
        elif isinstance(self.data, Settings) and name in self.data.keys():
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
        if isinstance(self.data, Controller):
            self.data.set_parameter(name, value, function_name=self.function_name)
        elif isinstance(self.data, dict):
            self.data[name] = value
        elif isinstance(self.data, Settings):
            self.data.set(name, value)

    def is_key(self, key):
        if isinstance(self.data, Controller):
            return key in self.data.get("parameters")[self.function_name]
        if isinstance(self.data, dict):
            return key in self.data
        if isinstance(self.data, Settings):
            return key in self.data.keys()
        return False

    def _get_widget_value(self) -> Any:
        pass

    def _set_widget_value(self, value):
        pass

    def init_ui(self, layout):
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
