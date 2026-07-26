"""Array parameter GUI."""

from __future__ import annotations

from typing import Any

import numpy as np
from qtpy.QtCore import QAbstractTableModel, Qt
from qtpy.QtWidgets import QHBoxLayout, QTableView, QTabWidget, QVBoxLayout, QWidget

from .param import Param


class _ArrayTableModel(QAbstractTableModel):
    """Table model for displaying a 2D numpy array slice.

    Parameters
    ----------
    data : numpy.ndarray
        A 1D or 2D array to display. 1D arrays are shown as a single column.
    """

    def __init__(self, data, **kwargs):
        super().__init__(**kwargs)
        arr = np.asarray(data)
        if arr.ndim == 1:
            arr = arr.reshape(-1, 1)
        self._data = arr

    def rowCount(self, parent=None):
        """Return the number of rows."""
        return self._data.shape[0]

    def columnCount(self, parent=None):
        """Return the number of columns."""
        return self._data.shape[1]

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        """Return display data for a given index."""
        if not index.isValid():
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return str(self._data[index.row(), index.column()])
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        """Return header data."""
        if role == Qt.ItemDataRole.DisplayRole:
            return str(section)
        return None


def _make_array_view(arr):
    """Recursively build a widget to display an N-D numpy array.

    Parameters
    ----------
    arr : numpy.ndarray
        Array to display. Must have ndim in [1, 5].

    Returns
    -------
    QWidget
        A QTableView for 1D/2D arrays, or a nested QTabWidget for 3D–5D.
    """
    if arr.ndim <= 2:
        view = QTableView()
        view.setModel(_ArrayTableModel(arr))
        return view
    tab_widget = QTabWidget()
    for i in range(arr.shape[0]):
        sub_widget = _make_array_view(arr[i])
        tab_widget.addTab(sub_widget, str(i))
    return tab_widget


class ArrayGui(Param):
    """Parameter GUI for displaying numpy arrays up to 5 dimensions.

    For 1D and 2D arrays, a QTableView is used directly.
    For 3D–5D arrays, a QTabWidget nests the sub-array views along axis 0,
    recursively down to 2D slices shown in QTableView.

    Parameters
    ----------
    **kwargs
        Additional keyword arguments passed to :class:`Param`.
    """

    data_type = np.ndarray

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self._array_container = QWidget()
        self._container_layout = QVBoxLayout()
        self._container_layout.setContentsMargins(0, 0, 0, 0)
        self._array_container.setLayout(self._container_layout)

        layout = QHBoxLayout()
        layout.addWidget(self._array_container)
        self.init_ui(layout)

    def _set_widget_value(self, value):
        # Clear previous widget
        while self._container_layout.count():
            item = self._container_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        arr = np.asarray(value)
        if arr.ndim == 0:
            arr = arr.reshape(1, 1)
        elif arr.ndim > 5:
            # Flatten dimensions beyond 5 into the last axis
            arr = arr.reshape(arr.shape[:4] + (-1,))

        widget = _make_array_view(arr)
        self._container_layout.addWidget(widget)

    def _get_widget_value(self):
        return self._value
