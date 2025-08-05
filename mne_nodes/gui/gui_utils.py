"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import json
import logging
import os
import sys
from functools import partial
from importlib import resources
from os.path import join

import darkdetect
from qtpy import compat
from qtpy.QtCore import Qt, QEvent
from qtpy.QtGui import QFont, QMouseEvent, QPalette, QColor, QIcon
from qtpy.QtTest import QTest
from qtpy.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QStyle,
    QInputDialog,
    QColorDialog,
    QFormLayout,
    QComboBox,
    QWidget,
)

import mne_nodes
from mne_nodes import _object_refs
from mne_nodes import extra
from mne_nodes.pipeline.pipeline_utils import is_test
from mne_nodes.pipeline.settings import Settings

# Load theme colors
theme_color_path = join(str(resources.files(extra)), "color_themes.json")
with open(theme_color_path) as file:
    theme_colors = json.load(file)


def center(widget):
    qr = widget.frameGeometry()
    cp = QApplication.primaryScreen().availableGeometry().center()
    qr.moveCenter(cp)
    widget.move(qr.topLeft())


def set_ratio_geometry(size_ratio, widget):
    """Set the geometry of a widget based on the screen size and a ratio.

    Parameters
    ----------
    size_ratio : tuple of float
        Enter the ratio of the current screen size to set the widget size, e.g. (0.5, 0.5) for half the width
        and height of the screen. If a single float is provided, it will be used for both width and height.
    widget : QWidget
        The widget to resize.
    """
    if not isinstance(size_ratio, tuple):
        size_ratio = (size_ratio, size_ratio)
    wratio, hratio = size_ratio
    if widget.screen() is None:
        geometry = QApplication.primaryScreen().availableGeometry()
    else:
        geometry = widget.screen().availableGeometry()
    width = int(geometry.width() * wratio)
    height = int(geometry.height() * hratio)
    widget.resize(width, height)

    return width, height


def get_std_icon(icon_name):
    return QApplication.instance().style().standardIcon(getattr(QStyle, icon_name))


# ToDo: Make PyQt-independent with tqdm


# ToDo: WIP


def ask_user(prompt):
    """Ask the user a question and return the answer (yes or no)."""
    if mne_nodes.gui_mode:
        parent = QApplication.activeWindow()
        ans = QMessageBox.question(parent, "Question", prompt)
        ok = ans in [QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No]
        ans = ans == QMessageBox.StandardButton.Yes
    elif is_test() or sys.stdin.isatty():
        ans = input(f"{prompt} (yes/no): ")
        ok = ans in ["yes", "y", "no", "n"]
        ans = ans.strip().lower() in ["yes", "y"]
    else:
        raise RuntimeError(
            "Input is not available in this environment. "
            "Please run the script in a terminal/command prompt or start the GUI."
        )
    if not ok or ans is None:
        warning_message = (
            "You need to provide an appropriate input to proceed (yes/n or no/n)!"
        )
    else:
        warning_message = None
    if warning_message is not None:
        if mne_nodes.gui_mode:
            parent = QApplication.activeWindow()
            QMessageBox().warning(parent, "Warning", warning_message)
        else:
            logging.warning(warning_message)
        return ask_user(prompt)

    return ans


def get_user_input(prompt, input_type="string", file_filter=None):
    """Get user input either via GUI or terminal, supporting string and path
    input.

    Parameters
    ----------
    prompt : str
        The prompt message to display to the user.
    input_type : str, optional
        The type of input to request: "string", "folder" or "file".
    file_filter : str, optional
        Set a filter for the file dialog, e.g. "JSON files (*.json)".

    Returns
    -------
    user_input : str or None
        The user input as a string, or None if cancelled or unavailable.

    Raises
    ------
    RuntimeError
        If input is not available in the current environment.
    ValueError
        If `input_type` is not "string" or "path".
    """
    type_error_message = f"input_type must be 'string' or 'path', not '{input_type}'"
    if mne_nodes.gui_mode:
        parent = QApplication.activeWindow()
        if input_type == "string":
            user_input, ok = QInputDialog.getText(parent, "Input String!", prompt)
        elif input_type == "folder":
            user_input = compat.getexistingdirectory(parent, prompt)
            ok = user_input != ""
        elif input_type == "file":
            user_input, ok = compat.getopenfilename(parent, prompt, filter=file_filter)
        else:
            raise ValueError(type_error_message)
    # Checks for interactive terminal
    elif sys.stdin.isatty():
        if input_type == "path":
            ans = input("Do you want to use the current directory? (y/n): ")
            if ans.lower() in ["y", "yes"]:
                user_input = os.getcwd()
                ok = True
            else:
                user_input = input(f"{prompt}: ")
                ok = True
        elif input_type == "string":
            user_input = input(f"{prompt}: ")
            ok = True
        else:
            raise ValueError(type_error_message)
    else:
        raise RuntimeError(
            "Input is not available in this environment. "
            "Please run the script in a terminal/command prompt or start the GUI."
        )

    # Check user input
    if not ok or user_input is None:
        warning_message = "You need to provide an appropriate input to proceed!"
    elif input_type == "folder" and not os.path.isdir(user_input):
        warning_message = "The provided path is not a valid directory!"
    elif input_type == "file" and not os.path.isfile(user_input):
        warning_message = "The provided path is not a valid file!"
    elif input_type == "string" and not isinstance(user_input, str):
        warning_message = "The provided input is not a valid string!"
    else:
        warning_message = None
    if warning_message is not None:
        if mne_nodes.gui_mode:
            parent = QApplication.activeWindow()
            QMessageBox().warning(parent, "Warning", warning_message)
        else:
            logging.warning(warning_message)
        return get_user_input(prompt, input_type)

    return user_input


def invert_rgb_color(color_tuple):
    return tuple(map(lambda i, j: i - j, (255, 255, 255), color_tuple))


def format_color(clr):
    """This converts a hex-color-string to a tuple of RGB-values."""
    if isinstance(clr, str):
        clr = clr.strip("#")
        return tuple(int(clr[i : i + 2], 16) for i in (0, 2, 4))
    return clr


def mouse_interaction(func):
    def wrapper(**kwargs):
        QTest.qWaitForWindowExposed(kwargs["widget"])
        QTest.qWait(10)
        func(**kwargs)
        QTest.qWait(10)

    return wrapper


@mouse_interaction
def mousePress(widget=None, pos=None, button=None, modifier=None):
    if modifier is None:
        modifier = Qt.KeyboardModifier.NoModifier
    event = QMouseEvent(
        QEvent.Type.MouseButtonPress, pos, button, Qt.MouseButton.NoButton, modifier
    )
    QApplication.sendEvent(widget, event)


@mouse_interaction
def mouseRelease(widget=None, pos=None, button=None, modifier=None):
    if modifier is None:
        modifier = Qt.KeyboardModifier.NoModifier
    event = QMouseEvent(
        QEvent.Type.MouseButtonRelease, pos, button, Qt.MouseButton.NoButton, modifier
    )
    QApplication.sendEvent(widget, event)


@mouse_interaction
def mouseMove(widget=None, pos=None, button=None, modifier=None):
    if button is None:
        button = Qt.MouseButton.NoButton
    if modifier is None:
        modifier = Qt.KeyboardModifier.NoModifier
    from qtpy.QtCore import QPoint

    if isinstance(pos, QPoint):
        pass
    event = QMouseEvent(
        QEvent.Type.MouseMove, pos, Qt.MouseButton.NoButton, button, modifier
    )
    QApplication.sendEvent(widget, event)


def mouseClick(widget, pos, button, modifier=None):
    mouseMove(widget=widget, pos=pos)
    mousePress(widget=widget, pos=pos, button=button, modifier=modifier)
    mouseRelease(widget=widget, pos=pos, button=button, modifier=modifier)


def mouseDrag(widget, positions, button, modifier=None):
    mouseMove(widget=widget, pos=positions[0])
    mousePress(widget=widget, pos=positions[0], button=button, modifier=modifier)
    for pos in positions[1:]:
        mouseMove(widget=widget, pos=pos, button=button, modifier=modifier)
    # For some reason moeve again to last position
    mouseMove(widget=widget, pos=positions[-1], button=button, modifier=modifier)
    mouseRelease(widget=widget, pos=positions[-1], button=button, modifier=modifier)


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

    colors = {k: QColor(v) for k, v in theme_colors[theme].items()}
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
    system_theme = darkdetect.theme().lower()
    if system_theme is None:
        logging.info("System theme detection failed. Using light theme.")
        system_theme = "light"
    return system_theme


def set_app_theme():
    app = QApplication.instance()
    app.setStyle("Fusion")
    app_theme = Settings().value("app_theme")
    # Detect system theme
    if app_theme == "auto":
        app_theme = _get_auto_theme()
    app.setPalette(get_palette(app_theme))
    # Set Icon
    if app_theme == "light":
        icon_name = "mne_pipeline_icon_light.png"
    else:
        icon_name = "mne_pipeline_icon_dark.png"
    # Set func-button color
    mw = _object_refs["main_window"]
    if mw is not None:
        for func_button in mw.bt_dict.values():
            if app_theme == "light":
                func_button.setStyleSheet(
                    "QPushButton:checked { background-color: #a3a3a3; }"
                )
            elif app_theme == "high_contrast":
                func_button.setStyleSheet(
                    "QPushButton:checked { background-color: #ffffff; }"
                )
            else:
                func_button.setStyleSheet(
                    "QPushButton:checked { background-color: #000000; }"
                )
    icon_path = join(str(resources.files(extra)), icon_name)
    app_icon = QIcon(str(icon_path))
    app.setWindowIcon(app_icon)


def set_app_font():
    app = QApplication.instance()
    font_family = Settings().value("app_font")
    font_size = Settings().value("app_font_size")
    app.setFont(QFont(font_family, font_size))


class ColorTester(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        _object_refs["color_tester"] = self
        theme = Settings().value("app_theme")
        if theme == "auto":
            theme = _get_auto_theme()
        self.theme = theme
        self.color_display = {}
        self.init_ui()

        self.show()

    def init_ui(self):
        layout = QFormLayout(self)
        self.theme_cmbx = QComboBox()
        self.theme_cmbx.addItems(["light", "dark", "high_contrast"])
        self.theme_cmbx.setCurrentText(self.theme)
        self.theme_cmbx.currentTextChanged.connect(self.change_theme)
        layout.addRow("Theme", self.theme_cmbx)
        for field_name in theme_colors[self.theme].keys():
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
        global theme_colors
        theme_colors[self.theme][field_name] = color.name()
        self.setPalette(get_palette(self.theme))
        self.color_display[field_name].setStyleSheet(
            f"background-color: {color.name()};"
            f"border-color: black;border-style: solid;border-width: 2px"
        )
        set_app_theme()

    def change_theme(self, theme):
        Settings().setValue("app_theme", theme)
        self.theme = theme
        set_app_theme()
        for field_name, color in theme_colors[theme].items():
            self.color_display[field_name].setStyleSheet(
                f"background-color: {color};"
                f"border-color: black;border-style: solid;border-width: 2px"
            )

    def closeEvent(self, event):
        with open(theme_color_path, "w") as file:
            json.dump(theme_colors, file, indent=4)
        event.accept()
