from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

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

_OUTPUT_FORMATS = ("hex", "rgb", "rgba")


class ColorGui(Param):
    """Parameter GUI for picking a single color.

    Parameters
    ----------
    output_format : "hex" | "rgb" | "rgba"
        String representation the picked color is stored/output as.
    """

    data_type = str

    def __init__(
        self, output_format: Literal["hex", "rgb", "rgba"] = "hex", **kwargs: Any
    ):
        if output_format not in _OUTPUT_FORMATS:
            raise ValueError(
                f"output_format must be one of {_OUTPUT_FORMATS}, "
                f"but got {output_format!r}."
            )
        self.output_format = output_format
        super().__init__(**kwargs)
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout()
        self.display_widget = QLabel()
        self.display_widget.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred
        )
        layout.addWidget(self.display_widget)
        self.param_widget = QPushButton("Pick Color")
        self.param_widget.clicked.connect(self._pick_color)
        layout.addWidget(self.param_widget)
        self.init_ui(layout)

    def _color_to_str(self, color) -> str:
        if self.output_format == "hex":
            return color.name()
        if self.output_format == "rgb":
            return f"rgb({color.red()}, {color.green()}, {color.blue()})"
        return (
            f"rgba({color.red()}, {color.green()}, {color.blue()}, "
            f"{round(color.alphaF(), 2)})"
        )

    def _open_color_dialog(self, previous_value: str | None):
        """Open a color picker dialog, pre-filled with *previous_value* if given."""
        kwargs = {"parent": self, "title": f"Pick a color for {self.name}"}
        if previous_value:
            kwargs["initial"] = _get_color(previous_value)
        return QColorDialog.getColor(**kwargs)

    def _pick_color(self):
        color = self._open_color_dialog(self._value)
        if color.isValid():
            self.value = self._color_to_str(color)

    def _set_widget_value(self, value):
        color = _get_color(value)
        pixmap = QPixmap(20, 20)
        pixmap.fill(color)
        self.display_widget.setPixmap(pixmap)
        self.display_widget.setToolTip(value)

    def _get_widget_value(self):
        return self._value


class ColorDictGui(ColorGui):
    """Parameter GUI for picking colors for a fixed set of keys, e.g. channel types."""

    data_type = dict

    def __init__(
        self, keys: dict[str, str] | Sequence[str] | str | None, **kwargs: Any
    ):
        self._keys_arg = keys
        super().__init__(**kwargs)

    def _init_ui(self):
        if isinstance(self._keys_arg, str):
            self.keys = self._load_from_data(self._keys_arg)
        else:
            self.keys = list(self._keys_arg) if self._keys_arg is not None else []
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
        key = self._get_selected_key()
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

    def _get_selected_key(self):
        text = self.select_widget.currentText()
        return next((key for key in self._cached_value if str(key) == text), text)

    def _pick_color(self):
        key = self._get_selected_key()
        previous_value = self._cached_value.get(key)
        color = self._open_color_dialog(previous_value)
        if color.isValid():
            self._cached_value[key] = self._color_to_str(color)
            self.value = self._cached_value
