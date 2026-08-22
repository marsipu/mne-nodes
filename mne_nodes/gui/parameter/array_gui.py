"""Array parameter GUI."""

from __future__ import annotations

from typing import Any

import numpy as np
from qtpy.QtCore import QAbstractTableModel, Qt
from qtpy.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QStackedLayout,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from .param import Param
from .utils import eval_param


class _ArraySliceModel(QAbstractTableModel):
    """Table model for displaying and editing a 2D numpy array slice.

    Parameters
    ----------
    data : numpy.ndarray | None
        A 2D array to display. If *None* an empty (0×0) array is used.
        1D arrays are reshaped to a single column.
    """

    def __init__(self, data=None, **kwargs):
        super().__init__(**kwargs)
        self._data = self._coerce(data)

    @staticmethod
    def _coerce(data):
        if data is None:
            return np.empty((0, 0))
        arr = np.asarray(data)
        if arr.ndim == 1:
            arr = arr.reshape(-1, 1)
        elif arr.ndim == 0:
            arr = arr.reshape(1, 1)
        return arr

    def replace_data(self, data):
        """Replace displayed slice without creating a new model."""
        self.beginResetModel()
        self._data = self._coerce(data)
        self.endResetModel()

    def rowCount(self, parent=None):
        """Return the number of rows."""
        return self._data.shape[0]

    def columnCount(self, parent=None):
        """Return the number of columns."""
        return self._data.shape[1] if self._data.ndim >= 2 else 1

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        """Return data for a given index."""
        if not index.isValid():
            return None
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return str(self._data[index.row(), index.column()])
        return None

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        """Edit a cell value."""
        if role == Qt.ItemDataRole.EditRole:
            try:
                self._data[index.row(), index.column()] = float(value)
                self.dataChanged.emit(index, index, [role])
                return True
            except (ValueError, TypeError):
                return False
        return False

    def flags(self, index):
        """All cells are editable."""
        return super().flags(index) | Qt.ItemFlag.ItemIsEditable

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        """Return numeric axis labels."""
        if role == Qt.ItemDataRole.DisplayRole:
            return str(section)
        return None


class ArrayGui(Param):
    """Parameter GUI for numpy arrays of up to 10 dimensions.

    Provides two input modes, switchable via a combo-box:

    **table**
        An editable :class:`~qtpy.QtWidgets.QTableView` that always shows the
        2-D slice selected by the dimension :class:`~qtpy.QtWidgets.QSpinBox`
        widgets (one per extra dimension beyond the last two).  Only the
        currently-visible cells are queried by Qt, so even arrays like
        300×20 000×5 000 remain responsive.  An empty array can be
        initialised when no value is present.

    **expr**
        A :class:`~qtpy.QtWidgets.QLineEdit` in which the user types any
        NumPy expression (``np`` is available in the evaluation namespace).
        The result is displayed next to the input field.

    Parameters
    ----------
    dtype : numpy dtype or type or None
        NumPy dtype to use for array values. If ``None``, preserve the input
        dtype.
    **kwargs
        Additional keyword arguments passed to :class:`Param`.
    """

    data_type = np.ndarray
    max_dimensions = 10

    def __init__(self, dtype: Any = None, **kwargs: Any):
        # Param.__init__ loads persisted data, including the expression cache.
        self._param_exp: str | None = None
        self.dtype = np.dtype(dtype) if dtype is not None else None
        super().__init__(**kwargs)

        # ── mode selector ──────────────────────────────────────────────────
        self._mode_cmbx = QComboBox()
        self._mode_cmbx.addItems(["table", "expr"])
        self._mode_cmbx.activated.connect(self._on_mode_changed)

        self._stack = QStackedLayout()

        # ── TABLE mode ─────────────────────────────────────────────────────
        self._table_widget = QWidget()
        table_outer = QVBoxLayout()
        table_outer.setContentsMargins(0, 0, 0, 0)

        # Row of spinboxes for extra dimensions
        self._spinbox_row = QWidget()
        self._spinbox_layout = QHBoxLayout()
        self._spinbox_layout.setContentsMargins(0, 0, 0, 0)
        self._spinbox_row.setLayout(self._spinbox_layout)
        self._spinboxes: list[QSpinBox] = []
        table_outer.addWidget(self._spinbox_row)

        # Table view (lazy – only renders visible cells)
        self._table_model = _ArraySliceModel()
        self._table_model.dataChanged.connect(self._on_table_data_changed)
        self._table_view = QTableView()
        self._table_view.setModel(self._table_model)
        table_outer.addWidget(self._table_view)
        self._table_widget.setLayout(table_outer)
        self._stack.addWidget(self._table_widget)

        # ── EXPR mode ──────────────────────────────────────────────────────
        self._expr_widget = QWidget()
        expr_grid = QGridLayout()
        expr_grid.setContentsMargins(0, 0, 0, 0)
        expr_grid.addWidget(QLabel("NumPy expression"), 0, 0)
        expr_grid.addWidget(QLabel("Result"), 0, 1)
        self._expr_edit = QLineEdit()
        self._expr_edit.setToolTip(
            "Enter a NumPy expression (np is available). Example: np.zeros((3, 4))"
        )
        self._expr_edit.editingFinished.connect(self._on_expr_changed)
        self._expr_display = QLabel()
        expr_grid.addWidget(self._expr_edit, 1, 0)
        expr_grid.addWidget(self._expr_display, 1, 1)
        self._expr_widget.setLayout(expr_grid)
        self._stack.addWidget(self._expr_widget)

        # ── parameter expression cache ───────────────────────────────────
        self._display_arr: np.ndarray | None = None

        # ── overall layout ─────────────────────────────────────────────────
        outer = QVBoxLayout()
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Input mode:"))
        mode_row.addWidget(self._mode_cmbx)
        mode_row.addStretch()
        outer.addLayout(mode_row)
        outer.addLayout(self._stack)
        self.init_ui(outer)

    # ── mode switching ─────────────────────────────────────────────────────

    @staticmethod
    def _validate_dimensions(value: np.ndarray) -> np.ndarray:
        arr = value
        if arr.ndim > ArrayGui.max_dimensions:
            raise ValueError(
                f"ArrayGui supports at most {ArrayGui.max_dimensions} dimensions; "
                f"got {arr.ndim}."
            )
        return arr

    def _convert_array(self, value) -> np.ndarray:
        """Convert *value* to the configured NumPy dtype."""
        return self._validate_dimensions(np.asarray(value, dtype=self.dtype))

    def _on_mode_changed(self, index: int):
        self._stack.setCurrentIndex(index)
        if index == 0 and self._display_arr is not None:
            self._refresh_table(self._display_arr)
        elif index == 1:
            exp = self._param_exp if self._param_exp is not None else ""
            self._expr_edit.setText(exp)

    # ── expr mode ──────────────────────────────────────────────────────────

    def _on_expr_changed(self):
        text = self._expr_edit.text()
        result = eval_param(text)
        if isinstance(result, np.ndarray):
            try:
                self.value = self._convert_array(result)
            except (TypeError, ValueError):
                self._expr_display.setText("Invalid expression")
            else:
                self._param_exp = text
        else:
            self._expr_display.setText("Invalid expression")

    # ── table mode helpers ─────────────────────────────────────────────────

    def _clear_spinboxes(self):
        for sb in self._spinboxes:
            self._spinbox_layout.removeWidget(sb)
            sb.deleteLater()
        self._spinboxes.clear()
        # remove labels too
        while self._spinbox_layout.count():
            item = self._spinbox_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _build_spinboxes(self, arr: np.ndarray):
        """Create one QSpinBox per extra dimension (ndim > 2)."""
        self._clear_spinboxes()
        n_extra = max(0, arr.ndim - 2)
        if n_extra == 0 or any(size == 0 for size in arr.shape[:n_extra]):
            self._spinbox_row.setVisible(False)
            return
        self._spinbox_row.setVisible(True)
        for dim in range(n_extra):
            label = QLabel(f"Dim {dim}:")
            self._spinbox_layout.addWidget(label)
            sb = QSpinBox()
            sb.setMinimum(0)
            sb.setMaximum(arr.shape[dim] - 1)
            sb.setToolTip(f"Axis {dim}, size {arr.shape[dim]}")
            sb.valueChanged.connect(self._on_spinbox_changed)
            self._spinbox_layout.addWidget(sb)
            self._spinboxes.append(sb)
        self._spinbox_layout.addStretch()

    def _current_slice(self, arr: np.ndarray) -> np.ndarray:
        """Return the 2-D slice selected by the current spinbox values."""
        n_extra = max(0, arr.ndim - 2)
        if any(size == 0 for size in arr.shape[:n_extra]):
            return np.empty((0, 0), dtype=arr.dtype)
        idx = tuple(sb.value() for sb in self._spinboxes)
        if idx:
            sliced = arr[idx]
        else:
            sliced = arr
        if sliced.ndim == 1:
            sliced = sliced.reshape(-1, 1)
        return sliced

    def _on_spinbox_changed(self):
        if self._display_arr is not None:
            slc = self._current_slice(self._display_arr)
            self._table_model.replace_data(slc)

    def _on_table_data_changed(self, *_):
        """Persist table edits and invalidate any expression cache."""
        if self._value is not None:
            self._param_exp = None
            self.value = np.array(self._value, copy=True)

    def _refresh_table(self, arr: np.ndarray):
        """Rebuild spinboxes and refresh the table for *arr*."""
        self._build_spinboxes(arr)
        slc = self._current_slice(arr)
        self._table_model.replace_data(slc)

    # ── Param interface ─────────────────────────────────────────────────────

    def _set_widget_value(self, value):
        arr = self._convert_array(value)
        self._display_arr = arr
        # Update table
        self._refresh_table(arr)
        # Update expr display
        exp = self._param_exp if self._param_exp is not None else repr(arr)
        self._expr_edit.setText(exp)
        self._expr_display.setText(str(arr.shape))

    def _get_widget_value(self):
        return self._value

    @property
    def value(self):
        """Return the current array value."""
        return super().value

    @value.setter
    def value(self, new_value):
        """Set the array value, evaluating string expressions via ``eval_param``."""
        if isinstance(new_value, str):
            self._param_exp = new_value
            new_value = eval_param(new_value)
            if not isinstance(new_value, np.ndarray):
                new_value = None
        if new_value is not None:
            new_value = self._convert_array(new_value)
        if new_value is None and not self.none_select:
            new_value = np.empty((0, 0))
        Param.value.fset(self, new_value)

    # ── expression persistence ──────────────────────────────────────────

    def _load_from_data(self, name):
        real_value = super()._load_from_data(name)
        if isinstance(real_value, np.ndarray):
            real_value = self._convert_array(real_value)
        exp_name = name + "_exp"
        if self.is_key(exp_name):
            # Expression metadata is a string, not an array parameter value.
            # Temporarily use its actual type so Param does not substitute the
            # ndarray default during validation.
            data_type = self.data_type
            try:
                self.data_type = str
                self._param_exp = super()._load_from_data(exp_name)
            finally:
                self.data_type = data_type
        return real_value

    def _save_to_data(self, name, value):
        super()._save_to_data(name, value)
        exp_name = name + "_exp"
        exp_value = self._param_exp if self._param_exp is not None else str(value)
        super()._save_to_data(exp_name, exp_value)
