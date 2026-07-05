from __future__ import annotations

from math import log10
from typing import Any

from qtpy.QtWidgets import QDoubleSpinBox, QHBoxLayout

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
        tuple_layout = QHBoxLayout()
        tuple_layout.addWidget(self.param_widget1)
        tuple_layout.addWidget(self.param_widget2)
        self.init_ui(tuple_layout)

    def _set_widget_value(self, value):
        if not len(value) == 2:
            raise ValueError(
                f"Expected a tuple of length 2, got {len(value)} elements."
            )
        self._external_set = True
        self.param_widget1.setValue(value[0])
        self.param_widget2.setValue(value[1])
        self._external_set = False
        self._on_widget_changed()

    def _get_widget_value(self):
        return self.param_widget1.value(), self.param_widget2.value()

    def _on_widget_changed(self):
        if not self._external_set:
            super()._on_widget_changed()
