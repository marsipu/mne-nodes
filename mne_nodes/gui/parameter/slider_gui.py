from __future__ import annotations

from ast import literal_eval
from typing import Any

from qtpy.QtCore import Qt
from qtpy.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QSizePolicy, QSlider

from .param import Param


class SliderGui(Param):
    data_type = int | float

    def __init__(
        self,
        min_val: float = 0.0,
        max_val: float = 100.0,
        step: float = 1.0,
        tracking: bool = True,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.min_val = min_val
        self.max_val = max_val
        self.param_widget = QSlider()
        self.param_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum
        )
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
            self.param_widget.setMinimum(int(self.min_val))
            self.param_widget.setMaximum(int(self.max_val))
        self.param_widget.setSingleStep(int(step))
        self.param_widget.setOrientation(Qt.Orientation.Horizontal)
        self.param_widget.setTracking(tracking)
        self.param_widget.setToolTip(
            f"MinValue = {min_val}\nMaxValue = {max_val}\nStep = {step}"
        )
        self.param_widget.valueChanged.connect(self._on_widget_changed)

        self.display_widget = QLineEdit()
        self.display_widget.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum
        )
        self.display_widget.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.display_widget.editingFinished.connect(self.display_edited)
        slider_layout = QHBoxLayout()
        slider_layout.addWidget(self.param_widget, stretch=10)
        slider_layout.addWidget(self.display_widget, stretch=1)
        if self.unit:
            slider_layout.addWidget(QLabel(self.unit))

        self.init_ui(slider_layout)

    def display_edited(self):
        try:
            new_value = literal_eval(self.display_widget.text())
        except (ValueError, SyntaxError):
            new_value = None
        if new_value is not None:
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
