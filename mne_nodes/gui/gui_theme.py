"""Shared Qt styles and theme definitions for MNE-Nodes GUI components."""

from importlib import resources
from os.path import join

import darkdetect
from qtpy.QtGui import QColor, QFont, QIcon, QPalette
from qtpy.QtWidgets import QApplication

from mne_nodes import extra
from mne_nodes.logger import logger
from mne_nodes.pipeline.settings import Settings

theme_colors = {
    "light": {
        "foreground": "#000000",
        "foreground_disabled": "#b8b8b8",
        "background": "#e6e6e6",
        "background_disabled": "#f0f0f0",
        "alternate_background": "#dddddd",
        "base": "#ffffff",
        "button": "#cbcbcb",
        "primary": "#0070b6",
        "border_light": "#888888",
        "border_midlight": "#aaaaaa",
        "border_dark": "#4b4b4b",
        "border_mid": "#666666",
        "border_shadow": "#333333",
        "link": "#ff00ff",
    },
    "dark": {
        "foreground": "#e5e5e5",
        "foreground_disabled": "#888888",
        "background": "#141414",
        "background_disabled": "#3e3e3e",
        "alternate_background": "#262626",
        "base": "#141414",
        "button": "#151515",
        "primary": "#0867cc",
        "border_light": "#888888",
        "border_midlight": "#aaaaaa",
        "border_dark": "#4b4b4b",
        "border_mid": "#666666",
        "border_shadow": "#333333",
        "link": "#ff00ff",
    },
    "high_contrast": {
        "foreground": "#ffffff",
        "foreground_disabled": "#A0A0A0",
        "background": "#000000",
        "background_disabled": "#4a4a4a",
        "alternate_background": "#222222",
        "base": "#0f0f0f",
        "button": "#000000",
        "primary": "#007ACC",
        "border_light": "#888888",
        "border_midlight": "#aaaaaa",
        "border_dark": "#4b4b4b",
        "border_mid": "#666666",
        "border_shadow": "#333333",
        "link": "#ff00ff",
    },
}


def get_palette(theme):
    color_roles = {
        "foreground": ["WindowText", "ToolTipText", "Text"],
        "foreground_disabled": ["PlaceholderText"],
        "background": ["Window", "HighlightedText"],
        "base": ["Base"],
        "button": ["Button"],
        "alternate_background": ["AlternateBase", "ToolTipBase"],
        "primary": ["ButtonText", "Highlight"],
        "border_light": ["Light"],
        "border_midlight": ["Midlight"],
        "border_dark": ["Dark"],
        "border_mid": ["Mid"],
        "border_shadow": ["Shadow"],
        "link": ["Link", "LinkVisited"],
    }
    color_roles_disabled = {
        "foreground_disabled": [
            "WindowText",
            "ButtonText",
            "Highlight",
            "Text",
            "Link",
            "LinkVisited",
        ],
        "background_disabled": ["Window", "HighlightedText", "AlternateBase", "Button"],
    }
    color_roles_inactive = {"primary": ["Highlight"], "foreground": ["HighlightedText"]}

    colors = {key: QColor(value) for key, value in theme_colors[theme].items()}
    palette = QPalette()
    for color_name, roles in color_roles.items():
        for role in roles:
            if hasattr(QPalette.ColorRole, role):
                palette.setColor(getattr(QPalette.ColorRole, role), colors[color_name])
    for color_name, roles in color_roles_disabled.items():
        for role in roles:
            if hasattr(QPalette.ColorRole, role):
                palette.setColor(
                    QPalette.ColorGroup.Disabled,
                    getattr(QPalette.ColorRole, role),
                    colors[color_name],
                )
    for color_name, roles in color_roles_inactive.items():
        for role in roles:
            if hasattr(QPalette.ColorRole, role):
                palette.setColor(
                    QPalette.ColorGroup.Inactive,
                    getattr(QPalette.ColorRole, role),
                    colors[color_name],
                )
    return palette


def _get_auto_theme():
    detected_theme = darkdetect.theme()
    if detected_theme is None:
        logger.info("System theme detection failed. Using light theme.")
        return "light"
    return detected_theme.lower()


def set_app_theme():
    app = QApplication.instance()
    app.setStyle(Settings().get("app_style"))
    app_theme = Settings().get("app_theme")
    if app_theme == "auto":
        app_theme = _get_auto_theme()
    app.setPalette(get_palette(app_theme))
    icon_name = (
        "mne_pipeline_icon_light.png"
        if app_theme == "light"
        else "mne_pipeline_icon_dark.png"
    )
    icon_path = join(str(resources.files(extra)), icon_name)
    app.setWindowIcon(QIcon(str(icon_path)))


def set_app_font_size(font_size=None):
    app = QApplication.instance()
    font = QFont()
    font.setFamilies(["Segoe UI", "Noto Sans", "Open Sans", "DejaVu Sans"])
    font.setPointSize(font_size or Settings().get("app_font_size"))
    app.setFont(font)


WELCOME_TOUR_STYLE = """
QWidget#WelcomeTourWidget {
    background-color: palette(base);
    border: 2px solid palette(highlight);
    border-radius: 12px;
}
QLabel#tourLabel {
    color: palette(text);
    font-size: 14px;
    font-weight: 600;
}
QPushButton {
    background-color: palette(button);
    color: palette(text);
    border: 1px solid palette(dark);
    border-radius: 6px;
    padding: 7px 13px;
    min-width: 52px;
}
QPushButton:hover {
    border-color: palette(highlight);
}
QPushButton#nextButton {
    background-color: palette(highlight);
    color: palette(highlighted-text);
    border-color: palette(highlight);
    font-weight: 700;
}
QPushButton#nextButton:hover {
    border-color: palette(highlighted-text);
}
QPushButton#finishButton {
    color: palette(highlight);
}
"""
