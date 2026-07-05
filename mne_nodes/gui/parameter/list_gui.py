from __future__ import annotations

from typing import Any

from qtpy.QtCore import Qt
from qtpy.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout

from mne_nodes.gui.widgets.list_widgets import EditList
from mne_nodes.gui.widgets.misc_widgets import SimpleDialog

from .param import Param
from .utils import convert_list_to_string


class ListGui(Param):
    data_type = list

    def __init__(
        self,
        show_edit_bt: bool = True,
        value_string_length: int | None = 30,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.show_edit_bt = show_edit_bt
        self.value_string_length = value_string_length
        self.cached_value = None
        if show_edit_bt:
            list_layout = QHBoxLayout()
            self.value_label = QLabel()
            list_layout.addWidget(self.value_label)
            self.param_widget = QPushButton("Edit")
            self.param_widget.setSizePolicy(
                QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum
            )
            self.param_widget.clicked.connect(self.open_dialog)
            list_layout.addWidget(
                self.param_widget, alignment=Qt.AlignmentFlag.AlignCenter
            )
        else:
            list_layout = QVBoxLayout()
            self.param_widget = EditList(data=self.value)
            list_layout.addWidget(self.param_widget)

        self.init_ui(list_layout)

    def open_dialog(self):
        dlg = SimpleDialog(
            EditList(self.value),
            self,
            title=f"Setting {self.alias}",
            window_title=self.alias,
        )
        dlg.finished.connect(self._update_param)
        dlg.open()

    def _set_widget_value(self, value):
        if value is not None:
            self.cached_value = value
        if self.show_edit_bt:
            self.value_label.setText(
                convert_list_to_string(value, self.unit, self.value_string_length)
            )
        else:
            self.param_widget.replace_data(value)

    def _get_widget_value(self):
        if self.value is None:
            if self.cached_value is not None:
                value = self.cached_value
            else:
                value = []
            if self.show_edit_bt:
                self.value_label.clear()
        else:
            value = self._value

        return value
