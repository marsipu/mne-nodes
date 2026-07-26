from __future__ import annotations

from typing import Any

from qtpy.QtWidgets import QHBoxLayout, QLabel, QLineEdit

from .param import Param


class StringGui(Param):
    data_type = str

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.param_widget = QLineEdit()
        self.param_widget.textChanged.connect(self._on_widget_changed)
        layout = QHBoxLayout()
        layout.addWidget(self.param_widget)
        if self.unit is not None:
            layout.addWidget(QLabel(self.unit))
        self.init_ui(layout)

    def _set_widget_value(self, value):
        self.param_widget.setText(value)

    def _get_widget_value(self):
        return self.param_widget.text()
