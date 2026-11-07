"""Application settings dialog built from the packaged TOML configuration."""

from functools import partial

from qtpy.QtCore import Signal
from qtpy.QtGui import QFontDatabase
from qtpy.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QStyleFactory,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from mne_nodes.backend.settings import Settings, settings_config
from mne_nodes.gui.parameter import BoolGui, ComboGui, FloatGui, IntGui, Param

_SETTING_WIDGETS: dict[str, type[Param]] = {
    "BoolGui": BoolGui,
    "ComboGui": ComboGui,
    "FloatGui": FloatGui,
    "IntGui": IntGui,
}


class SettingsDlg(QDialog):
    """Edit device-specific settings, saving changes immediately."""

    setting_changed = Signal(str, object)

    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.widgets: dict[str, Param] = {}
        layout = QVBoxLayout(self)
        notice = QLabel(
            "Changes are saved immediately. Settings marked below require a restart."
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)
        tabs = QTabWidget()
        layout.addWidget(tabs)
        tab_layouts: dict[str, QVBoxLayout] = {}
        for name, details in settings_config.items():
            tab = details["tab"]
            if tab not in tab_layouts:
                content = QWidget()
                tab_layouts[tab] = QVBoxLayout(content)
                tabs.addTab(content, tab)
            content_layout = tab_layouts[tab]
            kwargs = details.get("gui_kwargs", {}).copy()
            source = details.get("options_source")
            if source == "fonts":
                kwargs["options"] = QFontDatabase.families()
            elif source == "styles":
                kwargs["options"] = sorted(map(str.lower, QStyleFactory.keys()))
            elif source is not None:
                raise ValueError(f"Unknown settings options source: {source}")
            description = details["description"]
            if details.get("restart_required", False):
                description += " Restart required."
            widget = _SETTING_WIDGETS[details["gui_type"]](
                data=settings,
                name=name,
                default=settings.default(name),
                alias=details["alias"],
                description=description,
                parent_widget=content_layout.parentWidget(),
                groupbox_layout=False,
                **kwargs,
            )
            widget.paramChanged.connect(partial(self.setting_changed.emit, name))
            self.widgets[name] = widget
            content_layout.addWidget(widget)
        for content_layout in tab_layouts.values():
            content_layout.addStretch()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)
        self.resize(550, 650)

    def read_settings(self) -> None:
        """Reload values that may have changed through other application controls."""
        for widget in self.widgets.values():
            widget.read_param()
            widget._update_gui()
