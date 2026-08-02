from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from mne_qt_browser._pg_figure import _get_color
from qtpy.QtGui import QPixmap
from qtpy.QtWidgets import (
    QColorDialog,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
)

from .param import Param


class ColorGui(Param):
    data_type = dict

    def __init__(
        self, keys: dict[str, str] | Sequence[str] | str | None, **kwargs: Any
    ):
        super().__init__(**kwargs)

        if isinstance(keys, str):
            self.keys = self._load_from_data(keys)
        else:
            self.keys = list(keys) if keys is not None else []
        self._cached_value = None
        layout = QHBoxLayout()
        self.select_widget = QComboBox()
        self.select_widget.setEditable(True)
        self.select_widget.addItems([str(k) for k in self.keys])
        self.select_widget.activated.connect(self._change_display_color)
        layout.addWidget(self.select_widget)
        self.display_widget = QLabel()
        self.display_widget.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred
        )
        layout.addWidget(self.display_widget)
        self.param_widget = QPushButton("Pick Color")
        self.param_widget.clicked.connect(self._pick_color)
        layout.addWidget(self.param_widget)
        self.init_ui(layout)

    def _change_display_color(self):
        key = self.select_widget.currentText()
        if key in self._cached_value:
            color = _get_color(self._cached_value[key])
            pixmap = QPixmap(20, 20)
            pixmap.fill(color)
            self.display_widget.setPixmap(pixmap)
        else:
            self.display_widget.setText("None")

    def _set_widget_value(self, value):
        self._cached_value = value
        self.keys = value.keys()
        self._change_display_color()

    def _get_widget_value(self):
        return self._cached_value

    def _pick_color(self):
        key = self.select_widget.currentText()
        if key in self._cached_value:
            previous_color = _get_color(self._cached_value[key])
            color = QColorDialog.getColor(
                initial=previous_color,
                parent=self,
                title=f"Pick a color for {self.name}",
            )
        else:
            color = QColorDialog.getColor(
                parent=self, title=f"Pick a color for {self.name}"
            )
        self._cached_value[key] = color.name()
        self.value = self._cached_value
