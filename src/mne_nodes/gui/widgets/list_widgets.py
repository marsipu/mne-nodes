"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

from collections.abc import Hashable
from typing import ClassVar

from qtpy.QtCore import Qt, Signal
from qtpy.QtGui import QColor, QFont, QIcon
from qtpy.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListView,
    QPushButton,
    QSizePolicy,
    QStyledItemDelegate,
    QVBoxLayout,
)

from mne_nodes.backend.settings import Settings
from mne_nodes.gui.widget_models.list_models import (
    BaseListModel,
    CheckDictEditModel,
    CheckListModel,
    CheckListProgressModel,
    EditListModel,
    MarkListModel,
)
from mne_nodes.gui.widgets.base import BaseList
from mne_nodes.logger import logger


class SimpleList(BaseList):
    """A basic List-Widget to display the content of a list.

    Parameters
    ----------
    data : list[str] | None
        Input a list with contents to display.
    extended_selection: bool
        Set True, if you want to select more than one item in the list.
    show_index: bool
        Set True if you want to display the list-index in front of each value.
    parent : QWidget | None
        Parent Widget (QWidget or inherited) or None if there is no parent.
    title : str | None
        An optional title.

    Notes
    -----
    If you change the contents of data outside of this class,
    call content_changed to update this widget.
    If you change the reference to data, call the appropriate replace_data.
    """

    def __init__(
        self,
        data=None,
        extended_selection=False,
        show_index=False,
        parent=None,
        title=None,
    ):
        super().__init__(
            model=BaseListModel(data, show_index),
            view=QListView(),
            extended_selection=extended_selection,
            parent=parent,
            title=title,
        )


class EditList(BaseList):
    """An editable List-Widget to display and manipulate the content of a list.

    Parameters
    ----------
    data : list[str] | None
        Input a list with contents to display.
    ui_buttons : bool
        If to display Buttons or not.
    ui_button_pos: str
        The side on which to show the buttons,
         'right', 'left', 'top' or 'bottom'.
    show_index: bool
        Set True if you want to display the list-index in front of each value.
    parent : QWidget | None
        Parent Widget (QWidget or inherited) or None if there is no parent.
    title : str | None
        An optional title.
    model : QAbstractItemModel
        Provide an alternative to EditListModel.

    Notes
    -----
    If you change the contents of the list outside of this class,
     call content_changed to update this widget.
    If you change the reference to data, call replace_data.
    """

    def __init__(
        self,
        data=None,
        ui_buttons=True,
        ui_button_pos="right",
        extended_selection=False,
        show_index=False,
        parent=None,
        title=None,
        model=None,
    ):
        self.ui_buttons = ui_buttons
        self.ui_button_pos = ui_button_pos

        if model is None:
            model = EditListModel(data, show_index=show_index)

        super().__init__(
            model=model,
            view=QListView(),
            extended_selection=extended_selection,
            parent=parent,
            title=title,
        )

    def init_ui(self):
        if self.ui_button_pos in ["top", "bottom"]:
            layout = QVBoxLayout()
            bt_layout = QHBoxLayout()
        else:
            layout = QHBoxLayout()
            bt_layout = QVBoxLayout()

        if self.ui_buttons:
            addrow_bt = QPushButton("Add")
            addrow_bt.setSizePolicy(
                QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum
            )
            addrow_bt.clicked.connect(self.add_row)
            bt_layout.addWidget(addrow_bt)

            rmrow_bt = QPushButton("Remove")
            rmrow_bt.setSizePolicy(
                QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum
            )
            rmrow_bt.clicked.connect(self.remove_row)
            bt_layout.addWidget(rmrow_bt)

            edit_bt = QPushButton("Edit")
            edit_bt.setSizePolicy(
                QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum
            )
            edit_bt.clicked.connect(self.edit_item)
            bt_layout.addWidget(edit_bt)

            layout.addLayout(bt_layout)

        if self.ui_button_pos in ["top", "left"]:
            layout.addWidget(self.view)
        else:
            layout.insertWidget(0, self.view)

        if self.title:
            super_layout = QVBoxLayout()
            title_label = QLabel(self.title)
            title_label.setFont(QFont(Settings().get("app_font"), 14))
            super_layout.addWidget(title_label, alignment=Qt.AlignmentFlag.AlignHCenter)
            super_layout.addLayout(layout)
            self.setLayout(super_layout)
        else:
            self.setLayout(layout)

    # Todo: Add Rows at all possible positions
    def add_row(self):
        row = self.view.selectionModel().currentIndex().row() + 1
        if row == -1:
            row = 0
        self.model.insertRow(row)

    def remove_row(self):
        row_idxs = self.view.selectionModel().selectedRows()
        for row_idx in row_idxs:
            self.model.removeRow(row_idx.row())

    def edit_item(self):
        self.view.edit(self.view.selectionModel().currentIndex())


class CheckList(BaseList):
    """A Widget for a Check-List.

    Parameters
    ----------
    data : list[str] | None
        Input a list with contents to display.
    checked : list[str] | None
        Input a list, which will contain the checked items
        from data (and which intial items will be checked).
    ui_buttons : bool
        If to display Buttons or not.
    one_check : bool
        If only one Item in the CheckList can be checked at the same time.
    show_index: bool
        Set True if you want to display the list-index in front of each value.
    parent : QWidget | None
        Parent Widget (QWidget or inherited) or None if there is no parent.
    title : str | None
        An optional title
    model : QAbstractItemModel
        Provide an alternative to CheckListModel.

    Notes
    -----
    If you change the contents of data outside of this class,
     call content_changed to update this widget.
    If you change the reference to data, call replace_data or replace_checked.
    """

    checkedChanged = Signal(list)

    def __init__(
        self,
        data=None,
        checked=None,
        ui_buttons=True,
        ui_button_pos="right",
        one_check=False,
        show_index=False,
        parent=None,
        title=None,
        model=None,
    ):
        self.ui_buttons = ui_buttons
        self.ui_button_pos = ui_button_pos

        model = model or CheckListModel(data, checked, one_check, show_index)
        super().__init__(
            model=model,
            view=QListView(),
            extended_selection=False,
            parent=parent,
            title=title,
        )

        self.model.dataChanged.connect(self._checked_changed)

    def init_ui(self):
        if self.ui_button_pos in ["top", "bottom"]:
            layout = QVBoxLayout()
            bt_layout = QHBoxLayout()
        else:
            layout = QHBoxLayout()
            bt_layout = QVBoxLayout()

        if self.ui_buttons:
            all_bt = QPushButton("All")
            all_bt.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
            all_bt.clicked.connect(self.select_all)
            bt_layout.addWidget(all_bt)

            clear_bt = QPushButton("Clear")
            clear_bt.setSizePolicy(
                QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum
            )
            clear_bt.clicked.connect(self.clear_all)
            bt_layout.addWidget(clear_bt)

            layout.addLayout(bt_layout)

        if self.ui_button_pos in ["top", "left"]:
            layout.addWidget(self.view)
        else:
            layout.insertWidget(0, self.view)

        if self.title:
            super_layout = QVBoxLayout()
            title_label = QLabel(self.title)
            title_label.setFont(QFont(Settings().get("app_font"), 14))
            super_layout.addWidget(title_label, alignment=Qt.AlignmentFlag.AlignHCenter)
            super_layout.addLayout(layout)
            self.setLayout(super_layout)
        else:
            self.setLayout(layout)

    def _checked_changed(self):
        self.checkedChanged.emit(self.model._checked)
        logger.debug(f"Changed values: {self.model._checked}")

    def replace_checked(self, new_checked):
        """Replaces model._checked with new checked list."""
        self.model._checked = new_checked
        self.content_changed()

    def select_all(self):
        """Select all Items while leaving reference to model._checked
        intact."""
        for item in [i for i in self.model._data if i not in self.model._checked]:
            self.model._checked.append(item)
        # Inform Model about changes
        self.content_changed()
        self._checked_changed()

    def clear_all(self):
        """Deselect all Items while leaving reference to model._checked
        intact."""
        self.model._checked.clear()
        # Inform Model about changes
        self.content_changed()
        self._checked_changed()


class MarkList(BaseList):
    """Display dictionary keys and mark them with configurable icons.

    Parameters
    ----------
    data : dict[Hashable, str | bool] | None
        Items to display as keys, with string or boolean marks as values.
        Dictionary insertion order determines the display order.
    mark_icons : dict[str | bool, QIcon | str] | None
        Map marks to QIcon objects or QStyle.StandardPixmap names, such as
        "SP_DialogApplyButton". Defaults to the class-level mark_icons mapping.
        Values without a configured icon are displayed without a marking.
    extended_selection : bool
        Allow selecting multiple items.
    show_index: bool
        Set True if you want to display the list-index in front of each value.
    parent : QWidget | None
        Parent Widget (QWidget or inherited) or None if there is no parent.
    title : str | None
        An optional title.

    Notes
    -----
    If you change the contents of data outside of this class,
     call content_changed to update this widget.
    If you change the reference to data, call replace_data.
    Boolean marks default to apply/cancel icons. Override mark_icons on a
    subclass or pass an instance-specific mapping to configure other marks.
    """

    mark_icons: ClassVar[dict[str | bool, QIcon | str]] = {
        True: "SP_DialogApplyButton",
        False: "SP_DialogCancelButton",
    }

    def __init__(
        self,
        data: dict[Hashable, str | bool] | None = None,
        mark_icons: dict[str | bool, QIcon | str] | None = None,
        extended_selection: bool = False,
        show_index: bool = False,
        parent=None,
        title: str | None = None,
    ) -> None:
        icons = self.mark_icons if mark_icons is None else mark_icons
        super().__init__(
            model=MarkListModel(data, icons, show_index),
            view=QListView(),
            extended_selection=extended_selection,
            parent=parent,
            title=title,
        )

    def replace_data(self, new_data: dict[Hashable, str | bool]) -> None:
        """Replace the item-to-mark dictionary, retaining its reference."""
        self.model.set_data(new_data)
        self.content_changed()

    def content_changed(self) -> None:
        """Validate and refresh externally changed items or markings."""
        self.model.validate_data(self.model._data)
        super().content_changed()


class CheckDictEditList(EditList):
    """A List-Widget to display the items of a list and mark them depending of
    their appearance in check_dict.

    Parameters
    ----------
    data : list[str] | None
        A list with items to display.
    check_dict : dict | None
        A dictionary that may contain items from data as keys.
    ui_buttons : bool
        If to display Buttons or not.
    ui_button_pos: str
        The side on which to show the buttons,
         'right', 'left', 'top' or 'bottom'.
    show_index: bool
        Set True if you want to display the list-index in front of each value.
    yes_bt: str
        Supply the name for a qt-standard-icon to mark
         the items existing in check_dict.
    no_bt: str
        Supply the name for a qt-standard-icon to mark
        the items not existing in check_dict.
    parent : QWidget | None
        Parent Widget (QWidget or inherited) or None if there is no parent.
    title : str | None
        An optional title.

    Notes
    -----
    If you change the contents of data outside of this class,
     call content_changed to update this widget.
    If you change the reference to data, call replace_data.
    If you change the reference to check_dict, call replace_check_dict.

    Names for QT standard-icons:
    https://doc.qt.io/qt-5/qstyle.html#StandardPixmap-enum
    """

    def __init__(
        self,
        data=None,
        check_dict=None,
        ui_buttons=True,
        ui_button_pos="right",
        extended_selection=False,
        show_index=False,
        yes_bt=None,
        no_bt=None,
        parent=None,
        title=None,
    ):
        model = CheckDictEditModel(
            data, check_dict, show_index=show_index, yes_bt=yes_bt, no_bt=no_bt
        )
        super().__init__(
            data=data,
            ui_buttons=ui_buttons,
            ui_button_pos=ui_button_pos,
            extended_selection=extended_selection,
            show_index=show_index,
            parent=parent,
            title=title,
            model=model,
        )

    def replace_check_dict(self, new_check_dict=None):
        """Replaces model.check_dict with new check_dict."""
        if new_check_dict:
            self.model._check_dict = new_check_dict
        self.content_changed()


class ProgressDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        """Paint an item with a progress background while preserving native
        checkbox + text rendering.

        Notes
        -----
        On some styles/backends (notably on Windows), the incoming `option`
        isn't guaranteed to be fully initialized for checkable items, and
        mutating it can result in an empty text rect. We therefore copy and
        initialize a fresh option, paint our background, then delegate the
        actual item drawing to Qt.
        """
        progress = index.data(CheckListProgressModel.ProgressRole) or 0
        try:
            progress = int(progress)
        except (TypeError, ValueError):
            progress = 0
        progress = max(0, min(100, progress))

        # Copy + init style option so checkbox/text geometry is correct.
        self.initStyleOption(option, index)

        # Draw progress background first on copied rect
        bar_rect = option.rect.adjusted(0, 0, 0, 0)
        bar_rect.setWidth(int(bar_rect.width() * (progress / 100)))

        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#4CAF50"))
        painter.drawRect(bar_rect)
        painter.restore()

        # Let the base delegate draw checkbox + icon + text.
        super().paint(painter, option, index)

    def sizeHint(self, option, index):
        opt = type(option)(option)
        self.initStyleOption(opt, index)
        return super().sizeHint(opt, index)


class CheckListProgress(CheckList):
    """A List-Widget to display items with a progress bar for each item. The
    progress in progress_dict is updated on content_changed or by calling
    update_progress.

    Parameters
    ----------
    data : list[str]
        A list with items to display.
    checked : list[str] | None
        Input a list, which will contain the checked items
        from data (and which intial items will be checked).
    progress_dict : dict | None
        A dictionary that may contain items from data as keys and
        their progress (0-100) as values.
    ui_buttons : bool
        If to display Buttons or not.
    one_check : bool
        If only one Item in the CheckList can be checked at the same time.
    show_index: bool
        Set True if you want to display the list-index in front of each value.
    parent : QWidget | None
        Parent Widget (QWidget or inherited) or None if there is no parent.
    title : str | None
        An optional title
    """

    def __init__(
        self,
        data,
        checked=None,
        progress_dict=None,
        ui_buttons=True,
        ui_button_pos="right",
        one_check=False,
        show_index=False,
        parent=None,
        title=None,
    ):
        self.progress_dict = progress_dict or {i: 0 for i in data}
        model = CheckListProgressModel(
            data, checked, progress_dict, one_check=one_check, show_index=show_index
        )
        super().__init__(
            ui_buttons=ui_buttons,
            ui_button_pos=ui_button_pos,
            parent=parent,
            title=title,
            model=model,
        )
        self.view.setItemDelegate(ProgressDelegate(self.view))

    def update_progress(self, item, progress):
        """Update the progress of a specific item.

        Parameters
        ----------
        item : str
            The item to update the progress for.
        progress : int
            The new progress value (0-100).
        """
        self.progress_dict[item] = progress
        self.content_changed()
