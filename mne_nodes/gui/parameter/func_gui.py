from __future__ import annotations

from typing import Any

from qtpy.QtWidgets import QGridLayout, QLabel, QLineEdit

from .param import Param
from .utils import eval_param


class FuncGui(Param):
    data_type = object

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.param_exp = None
        self._cached_value = None
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
        if self.unit:
            func_layout.addWidget(QLabel(self.unit))
        self.init_ui(func_layout)

    def _set_widget_value(self, value):
        if hasattr(self, "param_exp") and self.param_exp is not None:
            self.param_widget.setText(str(self.param_exp))
            self.display_widget.setText(str(value)[:20])
        else:
            self.param_widget.setText(str(value))
            self.display_widget.setText(str(value)[:20])

    def _get_widget_value(self):
        if self._value is None:
            value = self._cached_value
        else:
            self.param_exp = self.param_widget.text()
            value = eval_param(self.param_exp)
        self.display_widget.setText(str(value)[:20])

        return value

    def _load_from_data(self, name):
        real_value = super()._load_from_data(name)

        exp_name = name + "_exp"
        if self.is_key(exp_name):
            exp_value = super()._load_from_data(exp_name)
        else:
            exp_value = None
        self.param_exp = exp_value

        return real_value

    def _save_to_data(self, name, value):
        super()._save_to_data(name, value)

        exp_name = name + "_exp"
        exp_value = self.param_exp if self.param_exp is not None else str(self._value)
        super()._save_to_data(exp_name, exp_value)

    @property
    def value(self):
        return super().value

    @value.setter
    def value(self, new_value):
        if new_value is None:
            self._cached_value = self._value
        elif isinstance(new_value, str):
            new_value = eval_param(new_value)
            self.param_exp = new_value
        else:
            self.param_exp = str(new_value)
        self._value = new_value

        self._update_param()
