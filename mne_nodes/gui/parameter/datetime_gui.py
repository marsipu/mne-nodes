"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Any, Literal

from qtpy.QtCore import QDate, QDateTime, QTime
from qtpy.QtWidgets import QDateEdit, QDateTimeEdit, QHBoxLayout, QTimeEdit

from .param import Param

_DATETIME_TYPES = {"datetime": datetime, "date": date, "time": time}
_DEFAULT_DISPLAY_FORMATS = {
    "datetime": "dd.MM.yyyy HH:mm:ss",
    "date": "dd.MM.yyyy",
    "time": "HH:mm:ss",
}


class DateTimeGui(Param):
    """Parameter GUI for selecting a ``datetime``, ``date`` or ``time`` value.

    Parameters
    ----------
    datetime_type : "datetime" | "date" | "time"
        Which kind of value to edit; selects the underlying Qt widget
        (``QDateTimeEdit``, ``QDateEdit`` or ``QTimeEdit`` respectively).
    min_value, max_value : datetime | date | time | None
        Optional bounds, must match *datetime_type*.
    display_format : str | None
        Qt display format string. Defaults to a sensible format per
        *datetime_type*.
    """

    def __init__(
        self,
        datetime_type: Literal["datetime", "date", "time"] = "datetime",
        min_value: datetime | date | time | None = None,
        max_value: datetime | date | time | None = None,
        display_format: str | None = None,
        **kwargs: Any,
    ):
        if datetime_type not in _DATETIME_TYPES:
            raise ValueError(
                f"datetime_type must be one of {list(_DATETIME_TYPES)}, "
                f"but got {datetime_type!r}."
            )
        self.datetime_type = datetime_type
        # Set before super().__init__(), which already loads the value.
        self.data_type = _DATETIME_TYPES[datetime_type]

        super().__init__(**kwargs)

        display_format = display_format or _DEFAULT_DISPLAY_FORMATS[datetime_type]
        if datetime_type == "datetime":
            self.param_widget = QDateTimeEdit()
            self.param_widget.setCalendarPopup(True)
            self.param_widget.setDisplayFormat(display_format)
            if min_value is not None:
                self.param_widget.setMinimumDateTime(self._to_qdatetime(min_value))
            if max_value is not None:
                self.param_widget.setMaximumDateTime(self._to_qdatetime(max_value))
            self.param_widget.dateTimeChanged.connect(self._on_widget_changed)
        elif datetime_type == "date":
            self.param_widget = QDateEdit()
            self.param_widget.setCalendarPopup(True)
            self.param_widget.setDisplayFormat(display_format)
            if min_value is not None:
                self.param_widget.setMinimumDate(self._to_qdate(min_value))
            if max_value is not None:
                self.param_widget.setMaximumDate(self._to_qdate(max_value))
            self.param_widget.dateChanged.connect(self._on_widget_changed)
        else:
            self.param_widget = QTimeEdit()
            self.param_widget.setDisplayFormat(display_format)
            if min_value is not None:
                self.param_widget.setMinimumTime(self._to_qtime(min_value))
            if max_value is not None:
                self.param_widget.setMaximumTime(self._to_qtime(max_value))
            self.param_widget.timeChanged.connect(self._on_widget_changed)

        layout = QHBoxLayout()
        layout.addWidget(self.param_widget)
        self.init_ui(layout)

    @staticmethod
    def _to_qdate(value: date) -> QDate:
        return QDate(value.year, value.month, value.day)

    @staticmethod
    def _to_qtime(value: time) -> QTime:
        return QTime(value.hour, value.minute, value.second)

    @classmethod
    def _to_qdatetime(cls, value: datetime) -> QDateTime:
        return QDateTime(cls._to_qdate(value), cls._to_qtime(value))

    def _set_widget_value(self, value):
        if self.datetime_type == "datetime":
            self.param_widget.setDateTime(self._to_qdatetime(value))
        elif self.datetime_type == "date":
            self.param_widget.setDate(self._to_qdate(value))
        else:
            self.param_widget.setTime(self._to_qtime(value))

    def _get_widget_value(self):
        if self.datetime_type == "datetime":
            qdt = self.param_widget.dateTime()
            qdate, qtime = qdt.date(), qdt.time()
            # QDateTimeEdit has no timezone concept; treat the value as UTC
            # to match the round-trip behavior of TypedJSONEncoder/type_json_hook.
            return datetime(
                qdate.year(),
                qdate.month(),
                qdate.day(),
                qtime.hour(),
                qtime.minute(),
                qtime.second(),
                tzinfo=UTC,
            )
        elif self.datetime_type == "date":
            qdate = self.param_widget.date()
            return date(qdate.year(), qdate.month(), qdate.day())
        else:
            qtime = self.param_widget.time()
            return time(qtime.hour(), qtime.minute(), qtime.second())
