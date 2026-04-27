"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

from __future__ import annotations

from copy import deepcopy
import sys

import pandas as pd
from qtpy.QtWidgets import (
    QApplication,
    QLabel,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from mne_nodes.gui.base_widgets import (
    AssignWidget,
    CheckDictEditList,
    CheckDictList,
    CheckList,
    CheckListProgress,
    EditDict,
    EditList,
    EditPandasTable,
    ShallowTreeWidget,
    SimpleDict,
    SimpleList,
    SimplePandasTable,
    TreeWidget,
)


class BaseWidgetTester(QWidget):
    """Visual tester for the base widgets used in the test suite."""

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Base Widget Tester")
        self._tabs = QTabWidget()
        self._build_tabs()
        self._init_ui()

    def _demo_data(self):
        return {
            "list": ["item1", "item2", "item3"],
            "checklist": ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"],
            "checkdict": ["item1", "item2", "item3"],
            "dict": {"key1": "value1", "key2": "value2", "key3": "value3"},
            "dataframe": pd.DataFrame({"A": [1, 2, 3], "B": [4, 5, 6], "C": [7, 8, 9]}),
            "tree_dict": {
                "level1_a": {"level2_a": "value_a", "level2_b": "value_b"},
                "level1_b": {
                    "level2_c": {"level3_a": "deep_value"},
                    "level2_d": "value_d",
                },
            },
            "group_tree": {"group_a": ["item_a1", "item_a2"], "group_b": ["item_b1"]},
            "assign_items": ["Athena", "Hephaistos", "Zeus", "Ares", "Aphrodite"],
            "assign_props": ["strong", "smart", "bossy", "fishy"],
            "assignments": {
                "Athena": "smart",
                "Hephaistos": "strong",
                "Zeus": "bossy",
                "Ares": "smart",
            },
            "progress": {f"item_{i}": 25 * i for i in range(5)},
        }

    def _wrap_widget(self, widget):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(widget)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(container)
        return scroll

    def _add_tab(self, title, widget):
        self._tabs.addTab(self._wrap_widget(widget), title)

    def _build_tabs(self):
        data = self._demo_data()

        self._add_tab(
            "SimpleList",
            SimpleList(
                data=deepcopy(data["list"]), extended_selection=True, title="SimpleList"
            ),
        )
        self._add_tab(
            "EditList",
            EditList(
                data=deepcopy(data["list"]),
                ui_button_pos="bottom",
                extended_selection=True,
                title="EditList",
            ),
        )
        self._add_tab(
            "CheckList",
            CheckList(data=deepcopy(data["checklist"]), checked=[], title="CheckList"),
        )
        self._add_tab(
            "CheckDictList",
            CheckDictList(
                data=deepcopy(data["checkdict"]),
                check_dict={"item1": "value1", "item3": "value3"},
                extended_selection=True,
                title="CheckDictList",
            ),
        )
        self._add_tab(
            "CheckDictEditList",
            CheckDictEditList(
                data=deepcopy(data["checkdict"]),
                check_dict={"item1": "value1", "item3": "value3"},
                title="CheckDictEditList",
            ),
        )
        self._add_tab(
            "SimpleDict", SimpleDict(data=deepcopy(data["dict"]), title="SimpleDict")
        )
        self._add_tab(
            "EditDict",
            EditDict(
                data=deepcopy(data["dict"]), ui_button_pos="left", title="EditDict"
            ),
        )
        self._add_tab(
            "SimplePandasTable",
            SimplePandasTable(
                data=deepcopy(data["dataframe"]), title="SimplePandasTable"
            ),
        )
        self._add_tab(
            "EditPandasTable",
            EditPandasTable(data=deepcopy(data["dataframe"]), title="EditPandasTable"),
        )
        self._add_tab(
            "TreeWidget",
            TreeWidget(data=deepcopy(data["tree_dict"]), title="TreeWidget"),
        )
        self._add_tab(
            "ShallowTreeWidget",
            ShallowTreeWidget(
                data=deepcopy(data["group_tree"]), checked=[], title="ShallowTreeWidget"
            ),
        )
        self._add_tab(
            "AssignWidget",
            AssignWidget(
                items=deepcopy(data["assign_items"]),
                properties=deepcopy(data["assign_props"]),
                assignments=deepcopy(data["assignments"]),
                properties_editable=True,
                title="AssignWidget",
            ),
        )
        self._add_tab(
            "CheckListProgress",
            CheckListProgress(
                data=[f"item_{i}" for i in range(5)],
                checked=[],
                progress_dict=deepcopy(data["progress"]),
                title="CheckListProgress",
            ),
        )

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Use the tabs to visually inspect the base widgets with the same kind of test data used in `test_base_widgets.py`."
            )
        )
        layout.addWidget(self._tabs)


if __name__ == "__main__":
    app = QApplication.instance() or QApplication(sys.argv)
    widget = BaseWidgetTester()
    widget.resize(1200, 900)
    widget.show()
    sys.exit(app.exec())
