from __future__ import annotations

from typing import Any

from mne_nodes.gui.widgets.list_widgets import EditList
from mne_nodes.gui.widgets.misc_widgets import SimpleDialog

from .list_gui import ListGui


class TupleGui(ListGui):
    """Edit a tuple of arbitrary length, reusing :class:`ListGui`'s dialog UI.

    :class:`ListGui`'s edit-widgets mutate their underlying list in place, which
    relies on the list stored as the parameter value and the list shown in the
    widget being the very same object. Since tuples are immutable, that trick
    can't work here: editing instead happens on a plain list copy which is
    converted back to a tuple once the dialog is closed. This only supports the
    button+dialog mode, so ``show_edit_bt`` must stay ``True``.
    """

    data_type = tuple

    def __init__(self, show_edit_bt: bool = True, **kwargs: Any):
        if not show_edit_bt:
            raise ValueError("TupleGui only supports show_edit_bt=True.")
        super().__init__(show_edit_bt=show_edit_bt, **kwargs)

    def open_dialog(self):
        value = self.value if self.value is not None else self.cached_value or []
        edit_list = list(value)
        dlg = SimpleDialog(
            EditList(edit_list),
            self,
            title=f"Setting {self.alias}",
            window_title=self.alias,
        )
        dlg.finished.connect(lambda: self.set_param(tuple(edit_list)))
        dlg.open()

    def _set_widget_value(self, value):
        super()._set_widget_value(list(value) if value is not None else value)

    def _get_widget_value(self):
        return tuple(super()._get_widget_value())
