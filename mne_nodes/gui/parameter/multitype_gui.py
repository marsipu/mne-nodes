from __future__ import annotations

from collections.abc import Sequence
from functools import reduce
from typing import Any

from qtpy.QtWidgets import QComboBox, QHBoxLayout, QSizePolicy, QStackedLayout

from .bool_gui import BoolGui
from .checklist_gui import CheckListGui
from .combo_gui import ComboGui
from .dict_gui import DictGui
from .dual_tuple_gui import DualTupleGui
from .float_gui import FloatGui
from .int_gui import IntGui
from .list_gui import ListGui
from .param import Param
from .slider_gui import SliderGui
from .string_gui import StringGui


class MultiTypeGui(Param):
    def __init__(
        self,
        types: Sequence[str] | None = None,
        type_kwargs: dict[str, dict[str, Any]] | None = None,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.types = (
            list(types)
            if types
            else [
                "int",
                "float",
                "bool",
                "str",
                "list",
                "dict",
                "tuple",
                "combo",
                "checklist",
                "slider",
            ]
        )
        self.type_defaults = {
            "int": 0,
            "float": 0.0,
            "bool": False,
            "str": "",
            "list": [],
            "dict": {},
            "tuple": (0, 0),
            "combo": "",
            "checklist": [],
            "slider": 0.0,
        }
        self.type_kwargs = type_kwargs or {
            "combo": {"options": [""], "editable": True},
            "checklist": {"options": [], "one_check": False},
        }

        self.gui_types = {
            "int": "IntGui",
            "float": "FloatGui",
            "bool": "BoolGui",
            "str": "StringGui",
            "list": "ListGui",
            "dict": "DictGui",
            "tuple": "DualTupleGui",
            "combo": "ComboGui",
            "checklist": "CheckListGui",
            "slider": "SliderGui",
        }
        self.gui_class_map = {
            "IntGui": IntGui,
            "FloatGui": FloatGui,
            "BoolGui": BoolGui,
            "StringGui": StringGui,
            "ListGui": ListGui,
            "DictGui": DictGui,
            "DualTupleGui": DualTupleGui,
            "ComboGui": ComboGui,
            "CheckListGui": CheckListGui,
            "SliderGui": SliderGui,
        }
        self.gui_widgets = {}
        self.type_layout = QHBoxLayout()

        if "type" in self.types or type in self.types:
            pass
        for t in self.types:
            if t not in self.gui_types:
                pass
        param_types = [
            self.gui_class_map[self.gui_types[t]].data_type for t in self.types
        ]
        self.data_type = reduce(lambda a, b: a | b, param_types)

        self.param_type = type(self.value).__name__
        if self.param_type == "NoneType":
            self.param_type = self.types[0]

        self.param_widget = None
        self.type_cmbx = QComboBox()
        self.type_cmbx.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum
        )
        self.type_cmbx.addItems(self.types)
        self.type_cmbx.activated.connect(self.change_type)
        self.type_cmbx.setCurrentText(self.param_type)
        self.type_layout.addWidget(self.type_cmbx)
        self.stack_layout = QStackedLayout()
        self.type_layout.addLayout(self.stack_layout)
        self._init_type_guis()
        self.init_ui(self.type_layout)

    def _init_type_guis(self):
        for type_name in self.types:
            gui_class_name = self.gui_types[type_name]
            gui_class = self.gui_class_map[gui_class_name]
            kwargs = {
                "data": {},
                "name": self.name,
                "function_name": self.function_name,
                "alias": self.alias,
                "default": self.type_defaults[type_name],
                "groupbox_layout": False,
                "none_select": False,
                "description": self.description,
                "unit": self.unit,
                "parent_widget": self,
            }
            if type_name in self.type_kwargs:
                kwargs.update(self.type_kwargs[type_name])
            gui_instance = gui_class(**kwargs)
            gui_instance.data = self.data
            gui_instance.paramChanged.connect(lambda x: self.paramChanged.emit(x))
            self.gui_widgets[type_name] = gui_instance
            self.stack_layout.addWidget(gui_instance)
        if self.param_type not in self.gui_widgets:
            self.param_widget = self.gui_widgets[self.types[0]]
        else:
            self.param_widget = self.gui_widgets[self.param_type]
        self.stack_layout.setCurrentWidget(self.param_widget)

    def change_type(self, type_idx):
        self.param_type = self.types[type_idx]
        self.param_widget = self.gui_widgets[self.param_type]
        self.stack_layout.setCurrentWidget(self.param_widget)
        if not isinstance(self._load_from_data(self.name), self.param_widget.data_type):
            if isinstance(self.default, self.param_widget.data_type):
                self._save_to_data(self.name, self.default)
            else:
                self._save_to_data(self.name, self.type_defaults[self.param_type])
        if isinstance(self.value, self.param_widget.data_type):
            self.param_widget.value = self.value

    def _set_widget_value(self, value):
        if not isinstance(value, self.param_widget.data_type):
            raise TypeError(
                f"Value must be of type {self.param_widget.data_type}, "
                f"but got {type(value)}"
            )
        self.param_widget.value = value

    def _get_widget_value(self):
        return self.param_widget.value
