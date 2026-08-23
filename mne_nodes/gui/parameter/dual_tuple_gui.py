from __future__ import annotations

from math import log10
from typing import Any

from qtpy.QtWidgets import QCheckBox, QDoubleSpinBox, QHBoxLayout

from .param import Param


class DualTupleGui(Param):
    data_type = tuple

    def __init__(
        self,
        min_val: float = -1000.0,
        max_val: float = 1000.0,
        step: float = 0.1,
        **kwargs: Any,
    ):
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
        if self.unit:
            self.param_widget1.setSuffix(f" {self.unit}")
        self.param_widget1.valueChanged.connect(self._on_widget_changed)

        self.param_widget2.setMinimum(min_val)
        self.param_widget2.setMaximum(max_val)
        self.param_widget2.setSingleStep(step)
        if self.unit:
            self.param_widget2.setSuffix(f" {self.unit}")
        self.param_widget2.valueChanged.connect(self._on_widget_changed)

        # Small checkboxes toggling each element between its numeric value and None.
        self.none_chkbx1 = QCheckBox()
        self.none_chkbx1.setChecked(True)
        self.none_chkbx1.setToolTip("Uncheck to set this value to None")
        self.none_chkbx1.toggled.connect(
            lambda checked: self._on_element_none_toggled(self.param_widget1, checked)
        )

        self.none_chkbx2 = QCheckBox()
        self.none_chkbx2.setChecked(True)
        self.none_chkbx2.setToolTip("Uncheck to set this value to None")
        self.none_chkbx2.toggled.connect(
            lambda checked: self._on_element_none_toggled(self.param_widget2, checked)
        )

        tuple_layout = QHBoxLayout()
        tuple_layout.addWidget(self.none_chkbx1)
        tuple_layout.addWidget(self.param_widget1)
        tuple_layout.addWidget(self.none_chkbx2)
        tuple_layout.addWidget(self.param_widget2)
        self.init_ui(tuple_layout)

    def _on_element_none_toggled(self, widget, checked):
        widget.setEnabled(checked)
        self._on_widget_changed()

    def _set_widget_value(self, value):
        if not len(value) == 2:
            raise ValueError(
                f"Expected a tuple of length 2, got {len(value)} elements."
            )
        self._external_set = True
        try:
            for val, widget, chkbx in (
                (value[0], self.param_widget1, self.none_chkbx1),
                (value[1], self.param_widget2, self.none_chkbx2),
            ):
                is_none = val is None
                chkbx.setChecked(not is_none)
                widget.setEnabled(not is_none)
                if not is_none:
                    widget.setValue(val)
        except TypeError:
            pass
        self._external_set = False
        self._on_widget_changed()

    def _get_widget_value(self):
        value1 = self.param_widget1.value() if self.none_chkbx1.isChecked() else None
        value2 = self.param_widget2.value() if self.none_chkbx2.isChecked() else None
        return value1, value2

    def _on_widget_changed(self):
        if not self._external_set:
            super()._on_widget_changed()
