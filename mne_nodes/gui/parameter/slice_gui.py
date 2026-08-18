from __future__ import annotations

from typing import Any

from qtpy.QtWidgets import QHBoxLayout, QLabel, QLineEdit

from .param import Param


def _parse_slice(text: str) -> slice:
    text = text.strip()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    parts = text.split(":")
    if len(parts) not in (2, 3):
        raise ValueError(f"Invalid slice expression: {text!r}")

    def _to_int(part: str) -> int | None:
        part = part.strip()
        return int(part) if part else None

    return slice(*(_to_int(part) for part in parts))


def _slice_to_text(value: slice) -> str:
    start = "" if value.start is None else str(value.start)
    stop = "" if value.stop is None else str(value.stop)
    if value.step is None:
        return f"{start}:{stop}"
    return f"{start}:{stop}:{value.step}"


class SliceGui(Param):
    """Parameter GUI to enter a slice as text, e.g. ``1:10:2`` or ``:5``."""

    data_type = slice

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.param_widget = QLineEdit()
        self.param_widget.setPlaceholderText("start:stop:step")
        self.param_widget.setToolTip(
            "Enter a slice as 'start:stop:step', e.g. '1:10:2', ':5' or '2:'."
        )
        self.param_widget.textChanged.connect(self._on_text_changed)
        layout = QHBoxLayout()
        layout.addWidget(self.param_widget)
        if self.unit is not None:
            layout.addWidget(QLabel(self.unit))
        self.init_ui(layout)

    def _on_text_changed(self):
        try:
            _parse_slice(self.param_widget.text())
        except (ValueError, TypeError):
            self.param_widget.setStyleSheet("QLineEdit { border: 1px solid red; }")
        else:
            self.param_widget.setStyleSheet("")
            self._on_widget_changed()

    def _set_widget_value(self, value):
        self.param_widget.setStyleSheet("")
        if not isinstance(value, slice):
            raise TypeError(f"Expected a slice, got {type(value).__name__}")
        self.param_widget.setText(_slice_to_text(value))

    def _get_widget_value(self):
        return _parse_slice(self.param_widget.text())
