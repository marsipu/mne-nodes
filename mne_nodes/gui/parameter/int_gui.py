from __future__ import annotations

from typing import Any

from qtpy.QtWidgets import QHBoxLayout, QSpinBox

from .param import Param


class IntGui(Param):
    data_type = int

    def __init__(
        self,
        min_val: int = 0,
        max_val: int = 1000,
        special_value_text: str | None = None,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)

        self.param_widget = QSpinBox()
        self.param_widget.setMinimum(min_val)
        self.param_widget.setMaximum(max_val)
        self.param_widget.setToolTip(f"MinValue = {min_val}\nMaxValue = {max_val}")
        if special_value_text:
            self.param_widget.setSpecialValueText(special_value_text)
        if self.unit:
            self.param_widget.setSuffix(f" {self.unit}")
        self.param_widget.valueChanged.connect(self._on_widget_changed)

        layout = QHBoxLayout()
        layout.addWidget(self.param_widget)
        self.init_ui(layout)

    def _set_widget_value(self, value):
        self.param_widget.setValue(int(value))

    def _get_widget_value(self):
        return self.param_widget.value()
