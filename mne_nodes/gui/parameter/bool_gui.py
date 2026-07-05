from __future__ import annotations

from typing import Any

from qtpy.QtWidgets import QCheckBox, QVBoxLayout

from .param import Param


class BoolGui(Param):
    data_type = bool

    def __init__(self, return_integer: bool = False, **kwargs: Any):
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
