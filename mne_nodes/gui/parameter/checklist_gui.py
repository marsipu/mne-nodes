from __future__ import annotations

from typing import Any, Sequence

from qtpy.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy

from mne_nodes.gui.widgets.list_widgets import CheckList
from mne_nodes.gui.widgets.misc_widgets import SimpleDialog

from .param import Param
from .utils import convert_list_to_string


class CheckListGui(Param):
    data_type = list

    def __init__(
        self,
        options: Sequence[str],
        value_string_length: int | None = 30,
        one_check: bool = False,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.options = options
        self.value_string_length = value_string_length
        self.one_check = one_check
        self.cached_value = None
        check_list_layout = QHBoxLayout()
        self.value_label = QLabel()
        check_list_layout.addWidget(self.value_label)
        self.param_widget = QPushButton("Edit")
        self.param_widget.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum
        )
        self.param_widget.clicked.connect(self.open_dialog)
        check_list_layout.addWidget(self.param_widget)
        self.init_ui(check_list_layout)

    def open_dialog(self):
        dlg = SimpleDialog(
            CheckList(data=self.options, checked=self.value, one_check=self.one_check),
            self,
            title=f"Setting {self.alias}",
            window_title=self.alias,
        )
        dlg.finished.connect(self._update_param)
        dlg.open()

    def change_options(self, options):
        self.options = options
        self._set_widget_value(self.value)

    def _set_widget_value(self, value):
        if value is not None:
            self.cached_value = value
        self.value_label.setText(
            convert_list_to_string(value, self.unit, self.value_string_length)
        )

    def _get_widget_value(self):
        if self.value is None:
            if self.cached_value:
                value = self.cached_value
            else:
                value = []
            self.value_label.clear()
        else:
            value = self._value

        return value
