"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import re

from qtpy.QtCore import Qt, QTimer
from qtpy.QtGui import QFont
from qtpy.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from mne_nodes import _widgets
from mne_nodes.gui.widgets.dict_widgets import EditDict
from mne_nodes.gui.widgets.list_widgets import CheckDictList, EditList, SimpleList
from mne_nodes.pipeline.settings import Settings


class ComboBox(QComboBox):
    def __init__(self, scrollable=False, **kwargs):
        self.scrollable = scrollable
        super().__init__(**kwargs)

    def wheelEvent(self, event):
        if self.scrollable:
            super().wheelEvent(event)


class SimpleDialog(QDialog):
    def __init__(
        self,
        widget,
        parent=None,
        modal=True,
        scroll=False,
        title=None,
        window_title=None,
        show_close_bt=True,
    ):
        parent = parent or _widgets["main_window"] or _widgets["viewer"]
        super().__init__(parent)

        # Make sure, the dialog is deleted when closed
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        layout = QVBoxLayout()

        if title:
            layout.addWidget(QLabel(title))

        if window_title:
            self.setWindowTitle(window_title)

        if scroll:
            scroll_area = QScrollArea()
            scroll_area.setWidget(widget)
            layout.addWidget(scroll_area)
        else:
            layout.addWidget(widget)

        if show_close_bt:
            close_bt = QPushButton("Close")
            close_bt.clicked.connect(self.close)
            layout.addWidget(close_bt)

        self.setLayout(layout)


class AssignWidget(QWidget):
    """Widget for assigning items to editable properties."""

    def __init__(
        self,
        items,
        properties,
        assignments,
        properties_editable=False,
        parent=None,
        title=None,
        subtitles=None,
    ):
        super().__init__(parent)
        self.title = title
        self.subtitles = subtitles

        self.items = items
        self.props = properties
        self.assignments = assignments
        self.props_editable = properties_editable

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        list_layout = QHBoxLayout()
        if self.subtitles is not None and len(self.subtitles) == 2:
            subtitle1, subtitle2 = self.subtitles
        else:
            subtitle1, subtitle2 = None, None

        self.items_w = CheckDictList(
            self.items, self.assignments, extended_selection=True, title=subtitle1
        )
        self.items_w.selectionChanged.connect(self.items_selected)
        list_layout.addWidget(self.items_w)

        if self.props_editable:
            self.props_w = EditList(
                self.props, extended_selection=False, title=subtitle2
            )
        else:
            self.props_w = SimpleList(
                self.props, extended_selection=False, title=subtitle2
            )
        list_layout.addWidget(self.props_w)
        layout.addLayout(list_layout)

        bt_layout = QHBoxLayout()
        assign_bt = QPushButton("Assign")
        assign_bt.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        assign_bt.setFont(QFont(Settings().get("app_font"), 13))
        assign_bt.clicked.connect(self.assign)
        bt_layout.addWidget(assign_bt)

        show_assign_bt = QPushButton("Show Assignments")
        show_assign_bt.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        show_assign_bt.setFont(QFont(Settings().get("app_font"), 13))
        show_assign_bt.clicked.connect(self.show_assignments)
        bt_layout.addWidget(show_assign_bt)
        layout.addLayout(bt_layout)

        if self.title:
            super_layout = QVBoxLayout()
            title_label = QLabel(self.title)
            title_label.setFont(QFont(Settings().get("app_font"), 14))
            super_layout.addWidget(title_label, alignment=Qt.AlignmentFlag.AlignHCenter)
            super_layout.addLayout(layout)
            self.setLayout(super_layout)
        else:
            self.setLayout(layout)

    def items_selected(self, selected):
        # Get all unique values of selected items
        values = {self.assignments[key] for key in selected if key in self.assignments}
        self.props_w.select(values)

    def assign(self):
        sel_items = self.items_w.get_selected()
        sel_prop = self.props_w.get_current()

        for item in sel_items:
            self.assignments[item] = sel_prop

        # Inform Model in CheckDict about change
        self.items_w.content_changed()

    def show_assignments(self):
        self._assignments_dialog = SimpleDialog(
            EditDict(self.assignments), parent=self, modal=False
        )
        self._assignments_dialog.show()


class TimedMessageBox(QMessageBox):
    def __init__(
        self, timeout=10, step_length=1000, title=None, text=None, *args, **kwargs
    ):
        super().__init__(*args, **kwargs)

        if title is not None:
            self.setWindowTitle(title)
        if text is not None:
            self.setText(text)

        self._got_clicked = False
        self.buttonClicked.connect(lambda: setattr(self, "_got_clicked", True))

        self.timeout = timeout
        self._update_timeout_text()

        # Start timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.countdown)
        self.timer.start(step_length)

    def _update_timeout_text(self):
        text = self.text()
        match = re.match(r"(.*)\nTimeout: \d+", text)
        if match:
            text = match.group(1)
        self.setText(f"{text}\nTimeout: {self.timeout}")

    def countdown(self):
        self._update_timeout_text()
        self.timeout -= 1
        if self.timeout <= 0:
            self.timer.stop()
            if self.defaultButton() is not None:
                self.defaultButton().click()
            else:
                self.close()

    @staticmethod
    def _static_setup(icon, timeout, parent, title, text, buttons, defaultButton):
        cls = TimedMessageBox(
            timeout=timeout, title=title, text=text, icon=icon, parent=parent
        )

        cls._update_timeout_text()
        cls.setStandardButtons(buttons)
        cls.setDefaultButton(defaultButton)
        ans = cls.exec()

        # Make sure ans is the default button if timeout is reached
        if not cls._got_clicked:
            ans = cls.defaultButton()

        return ans

    @staticmethod
    def critical(
        timeout=10,
        parent=None,
        title=None,
        text=None,
        buttons=QMessageBox.StandardButton.Ok,
        defaultButton=QMessageBox.StandardButton.NoButton,
    ):
        return TimedMessageBox._static_setup(
            QMessageBox.Icon.Critical,
            timeout,
            parent,
            title,
            text,
            buttons,
            defaultButton,
        )

    @staticmethod
    def information(
        timeout=10,
        parent=None,
        title=None,
        text=None,
        buttons=QMessageBox.StandardButton.Ok,
        defaultButton=QMessageBox.StandardButton.NoButton,
    ):
        return TimedMessageBox._static_setup(
            QMessageBox.Icon.Information,
            timeout,
            parent,
            title,
            text,
            buttons,
            defaultButton,
        )

    @staticmethod
    def question(
        timeout=10,
        parent=None,
        title=None,
        text=None,
        buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        defaultButton=QMessageBox.StandardButton.No,
    ):
        return TimedMessageBox._static_setup(
            QMessageBox.Icon.Question,
            timeout,
            parent,
            title,
            text,
            buttons,
            defaultButton,
        )

    @staticmethod
    def warning(
        timeout=10,
        parent=None,
        title=None,
        text=None,
        buttons=QMessageBox.StandardButton.Ok,
        defaultButton=QMessageBox.StandardButton.NoButton,
    ):
        return TimedMessageBox._static_setup(
            QMessageBox.Icon.Warning,
            timeout,
            parent,
            title,
            text,
            buttons,
            defaultButton,
        )
