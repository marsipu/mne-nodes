from __future__ import annotations

from typing import Any

import pandas as pd
from qtpy import compat
from qtpy.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy

from mne_nodes.gui.dialogs import ErrorDialog
from mne_nodes.gui.widgets.misc_widgets import SimpleDialog
from mne_nodes.gui.widgets.pandas_widgets import (
    DATAFRAME_FILE_FILTERS,
    EditPandasTable,
    read_dataframe_file,
)
from mne_nodes.pipeline.exception_handling import get_exception_tuple

from .param import Param


class DataFrameGui(Param):
    """Parameter GUI to edit a pandas DataFrame or load one from a csv/xlsx file."""

    data_type = pd.DataFrame

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.cached_value = None
        self._edit_table = None

        df_layout = QHBoxLayout()
        self.value_label = QLabel()
        df_layout.addWidget(self.value_label)

        self.edit_bt = QPushButton("Edit")
        self.edit_bt.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum
        )
        self.edit_bt.clicked.connect(self.open_dialog)
        df_layout.addWidget(self.edit_bt)

        self.param_widget = QPushButton("Load")
        self.param_widget.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum
        )
        self.param_widget.clicked.connect(self.load_file)
        df_layout.addWidget(self.param_widget)

        self.init_ui(df_layout)

    def open_dialog(self):
        self._edit_table = EditPandasTable(self.value)
        dlg = SimpleDialog(
            self._edit_table,
            self,
            title=f"Setting {self.alias}",
            window_title=self.alias,
        )
        dlg.finished.connect(self._dialog_closed)
        dlg.open()

    def _dialog_closed(self):
        self.value = self._edit_table.update_data()
        self._edit_table = None

    def load_file(self):
        path, _ = compat.getopenfilename(
            self, f"Load {self.alias}", filters=DATAFRAME_FILE_FILTERS
        )
        if not path:
            return
        try:
            data = read_dataframe_file(path)
        except Exception:  # noqa: BLE001
            ErrorDialog(get_exception_tuple(), self, f"Could not load {path}").open()
            return
        self.value = data

    def _set_widget_value(self, value):
        if value is not None:
            self.cached_value = value
        if value is None:
            self.value_label.clear()
        else:
            self.value_label.setText(f"{value.shape[0]} rows x {value.shape[1]} cols")

    def _get_widget_value(self):
        if self.value is None:
            if self.cached_value is not None:
                value = self.cached_value
            else:
                value = pd.DataFrame()
        else:
            value = self.value

        return value
