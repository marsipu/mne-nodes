from __future__ import annotations

from typing import Any

from qtpy.QtWidgets import QDoubleSpinBox, QHBoxLayout

from .param import Param


class FloatGui(Param):
    data_type = float

    def __init__(
        self,
        min_val: float = -1000.0,
        max_val: float = 1000.0,
        step: float = 0.1,
        decimals: int = 2,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.param_widget = QDoubleSpinBox()
        self.param_widget.setMinimum(min_val)
        self.param_widget.setMaximum(max_val)
        self.param_widget.setSingleStep(step)
        self.param_widget.setDecimals(decimals)
        self.param_widget.setToolTip(f"MinValue = {min_val}\nMaxVal = {max_val}")
        if self.unit:
            self.param_widget.setSuffix(f" {self.unit}")
        self.param_widget.valueChanged.connect(self._on_widget_changed)

        layout = QHBoxLayout()
        layout.addWidget(self.param_widget)
        self.init_ui(layout)

    def _set_widget_value(self, value):
        self.param_widget.setValue(float(value))

    def _get_widget_value(self):
        return self.param_widget.value()
