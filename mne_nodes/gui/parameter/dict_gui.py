from __future__ import annotations

from typing import Any

from qtpy.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy

from mne_nodes.gui.widgets.dict_widgets import EditDict
from mne_nodes.gui.widgets.misc_widgets import SimpleDialog

from .param import Param
from .utils import convert_dict_to_string


class DictGui(Param):
    data_type = dict

    def __init__(self, value_string_length: int | None = 30, **kwargs: Any):
        super().__init__(**kwargs)
        self.value_string_length = value_string_length
        self.cached_value = None

        dict_layout = QHBoxLayout()
        self.value_label = QLabel()
        dict_layout.addWidget(self.value_label)
        self.param_widget = QPushButton("Edit")
        self.param_widget.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum
        )
        self.param_widget.clicked.connect(self.open_dialog)
        dict_layout.addWidget(self.param_widget)
        self.init_ui(dict_layout)

    def open_dialog(self):
        dlg = SimpleDialog(
            EditDict(self.value),
            self,
            title=f"Setting {self.alias}",
            window_title=self.alias,
        )
        dlg.finished.connect(self._update_param)
        dlg.open()

    def _set_widget_value(self, value):
        if value is not None:
            self.cached_value = value
        self.value_label.setText(
            convert_dict_to_string(value, self.unit, self.value_string_length)
        )

    def _get_widget_value(self):
        if self.value is None:
            if self.cached_value:
                value = self.cached_value
            else:
                value = {}
            self.value_label.clear()
        else:
            value = self.value

        return value
