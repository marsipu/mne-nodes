from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from qtpy import compat
from qtpy.QtWidgets import QHBoxLayout, QLabel, QPushButton

from .param import Param


class PathGui(Param):
    data_type = Path

    def __init__(self, pick_mode: Literal["file", "directory"] = "file", **kwargs: Any):
        super().__init__(**kwargs)

        self.pick_mode = pick_mode
        self._path = None
        layout = QHBoxLayout()
        self.display_widget = QLabel()
        layout.addWidget(self.display_widget)
        self.param_widget = QPushButton("Pick Path")
        self.param_widget.clicked.connect(self._pick_path)
        layout.addWidget(self.param_widget)
        self.init_ui(layout)

    def _pick_path(self):
        if self.pick_mode == "file":
            self._path = compat.getopenfilename(self, self.description)[0]
        else:
            self._path = compat.getexistingdirectory(self, self.description)
        self.value = self._path

    def _set_widget_value(self, value):
        self._path = value
        self.display_widget.setText(str(value))

    def _get_widget_value(self):
        return self._path
