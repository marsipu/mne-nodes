from __future__ import annotations

import logging
from typing import Any, Sequence

from qtpy.QtWidgets import QComboBox, QHBoxLayout, QLabel

from mne_nodes.gui.widgets.misc_widgets import ComboBox

from .param import Param


class ComboGui(Param):
    data_type = str

    def __init__(self, options: Sequence[str], editable: bool = False, **kwargs: Any):
        super().__init__(**kwargs)
        self.options = list(options)
        self.param_widget = ComboBox(scrollable=False)
        self.param_widget.setEditable(editable)
        self.param_widget.setInsertPolicy(QComboBox.InsertPolicy.InsertAtBottom)
        self.param_widget.setPlaceholderText("Select an option")
        self.param_widget.activated.connect(self._on_widget_changed)
        self._init_options()
        layout = QHBoxLayout()
        layout.addWidget(self.param_widget)
        if self.unit is not None:
            layout.addWidget(QLabel(self.unit))
        self.init_ui(layout)

    def _init_options(self):
        self.param_widget.clear()
        for option in self.options:
            if not isinstance(option, str):
                raise RuntimeError(
                    f"Options for {self.name} must be strings, "
                    f"but got type:{type(option)} for  {option}"
                )
            self.param_widget.addItem(str(option))

    def _set_widget_value(self, value):
        if not isinstance(value, str):
            value = str(value)
        if value not in self.options:
            logging.info(
                f"Value '{value}' not in options for {self.alias}. "
                "Adding it to the options."
            )
            self.options.append(value)
            self._init_options()
        self.param_widget.setCurrentText(value)

    def _get_widget_value(self):
        value = self.param_widget.currentText()
        if value not in self.options:
            self.options.append(value)
        return value
