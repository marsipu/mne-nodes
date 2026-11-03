"""Dialog for previewing and editing application theme colors."""

import json
from functools import partial
from importlib.resources import files

from qtpy.QtGui import QColor
from qtpy.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from mne_nodes import resources
from mne_nodes.backend.settings import Settings
from mne_nodes.gui.gui_theme import (
    _get_auto_theme,
    get_palette,
    set_app_theme,
    theme_colors,
)


class ColorTester(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        theme = Settings().get("app_theme")
        if theme == "auto":
            theme = _get_auto_theme()
        self.theme = theme
        self.color_display = {}
        self.init_ui()
        self.theme_color_path = files(resources) / "color_themes.json"

        self.show()

    def init_ui(self):
        layout = QFormLayout(self)
        self.theme_cmbx = QComboBox()
        self.theme_cmbx.addItems(["light", "dark", "high_contrast"])
        self.theme_cmbx.setCurrentText(self.theme)
        self.theme_cmbx.currentTextChanged.connect(self.change_theme)
        layout.addRow("Theme", self.theme_cmbx)
        for field_name in theme_colors[self.theme]:
            button_widget = QWidget()
            button_layout = QHBoxLayout(button_widget)
            button_display = QLabel()
            self.color_display[field_name] = button_display
            button_display.setFixedSize(20, 20)
            button_display.setStyleSheet(
                f"background-color: {theme_colors[self.theme][field_name]};"
                f"border-color: black;border-style: solid;border-width: 2px"
            )
            button_layout.addWidget(button_display)
            button = QPushButton("Change Color")
            button.clicked.connect(partial(self.open_color_dlg, field_name))
            button_layout.addWidget(button)
            layout.addRow(field_name, button_widget)

    def open_color_dlg(self, field_name):
        color_dlg = QColorDialog(self)
        color = QColor(theme_colors[self.theme][field_name])
        color_dlg.setCurrentColor(color)
        color_dlg.colorSelected.connect(lambda c: self.change_color(field_name, c))
        color_dlg.open()

    def change_color(self, field_name, color):
        theme_colors[self.theme][field_name] = color.name()
        self.setPalette(get_palette(self.theme))
        self.color_display[field_name].setStyleSheet(
            f"background-color: {color.name()};"
            f"border-color: black;border-style: solid;border-width: 2px"
        )
        set_app_theme()

    def change_theme(self, theme):
        Settings().set("app_theme", theme)
        self.theme = theme
        set_app_theme()
        for field_name, color in theme_colors[theme].items():
            self.color_display[field_name].setStyleSheet(
                f"background-color: {color};"
                f"border-color: black;border-style: solid;border-width: 2px"
            )

    def closeEvent(self, event):
        with open(self.theme_color_path, "w") as file:
            json.dump(theme_colors, file, indent=4)
        event.accept()
