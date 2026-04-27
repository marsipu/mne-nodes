"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import json
import logging
import os
import sys
from functools import partial
from importlib import resources
from os.path import join
from pathlib import Path

import darkdetect
from qtpy import compat
from qtpy.QtCore import QEvent, QPoint, Qt
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

from mne_nodes import extra, _widgets, main_widget, gui_mode
from mne_nodes.pipeline.settings import Settings


def center(widget):
    qr = widget.frameGeometry()
    cp = QApplication.primaryScreen().availableGeometry().center()
    qr.moveCenter(cp)
    widget.move(qr.topLeft())


def set_ratio_geometry(size_ratio, widget):
    """Set the geometry of a widget based on the screen size and a ratio.

    Parameters
    ----------
    size_ratio : float or tuple of float
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


def ask_user(prompt, cancel_allowed=True, close_on_cancel=False, parent=None):
    """Ask the user a yes or no question.

    The answer is returned as a boolean. If the user cancels the
    operation, None is returned.

    Parameters
    ----------
    prompt : str
        The prompt message to display to the user.
    cancel_allowed : bool, optional
        If True, allows the user to cancel the operation. Defaults to True.
    close_on_cancel : bool, optional
        If True, the app exits after cancel. Defaults to False.
    parent : QWidget | None, optional
        Set the parent of the modal widget.
    """
    if gui_mode:
        parent = parent or main_widget()
        if cancel_allowed:
            buttons = (
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
                | QMessageBox.StandardButton.Cancel
            )
        else:
            buttons = QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ans = QMessageBox.question(parent, "Question", prompt, buttons=buttons)
        ok = ans in [QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No]
        cancel = ans == QMessageBox.StandardButton.Cancel
        ans = ans == QMessageBox.StandardButton.Yes
    else:
        if cancel_allowed:
            prompt += " (yes/no/cancel): "
        else:
            prompt += " (yes/no): "
        # Use input() for terminal interaction
        ans = input(f"{prompt} (yes/no): ")
        ok = ans in ["yes", "y", "no", "n"]
        cancel = ans in ["cancel", "c"]
        ans = ans.strip().lower() in ["yes", "y"]
    if cancel and cancel_allowed:
        if close_on_cancel:
            logging.info("User canceled, closing app.")
            sys.exit(0)
        else:
            logging.info("User cancelled the operation.")
            return None
    if not ok or ans is None:
        warning_message = (
            "You need to provide an appropriate input to proceed (yes/n or no/n)!"
        )
    else:
        warning_message = None
    if warning_message is not None:
        if gui_mode:
            parent = main_widget()
            QMessageBox().warning(parent, "Warning", warning_message)
        else:
            logging.warning(warning_message)
        return ask_user(prompt)

    return ans


def ask_user_custom(
    prompt, buttons=None, cancel_allowed=True, close_on_cancel=False, parent=None
):
    """Ask the user a question with custom labels.

    If exactly two labels are provided, this keeps backward compatible
    behavior and returns a boolean (`True` for the first label,
    `False` for the second label). If more than two labels are provided,
    the selected label is returned. If the user cancels the operation,
    None is returned.

    Parameters
    ----------
    prompt : str
        The prompt message to display to the user.
    buttons : list[str] | tuple[str, ...] | None
        Labels for decision buttons. If None, defaults to ["yes", "no"].
    cancel_allowed : bool, optional
        If True, allows the user to cancel the operation. Defaults to True.
    close_on_cancel : bool, optional
        If True, the app exits after cancel. Defaults to False.
    parent : QWidget | None, optional
        Set the parent of the modal widget.
    """
    if buttons is None:
        button_labels = ["yes", "no"]
    else:
        button_labels = list(buttons)
    if len(button_labels) < 2:
        raise ValueError("buttons must contain at least two labels")

    label_map = {
        label.strip().lower(): label
        for label in button_labels
        if isinstance(label, str) and label.strip()
    }
    if len(label_map) != len(button_labels):
        raise ValueError("buttons must contain unique, non-empty string labels")

    normalized_labels = list(label_map.keys())
    first_label = button_labels[0]
    second_label = button_labels[1]

    if gui_mode:
        parent = parent or main_widget()
        msg_box = QMessageBox(parent)
        msg_box.setWindowTitle("Question")
        msg_box.setText(prompt)
        qt_buttons = {}
        for idx, label in enumerate(button_labels):
            if idx == 0:
                role = QMessageBox.ButtonRole.YesRole
            elif idx == 1:
                role = QMessageBox.ButtonRole.NoRole
            else:
                role = QMessageBox.ButtonRole.ActionRole
            qt_button = msg_box.addButton(label, role)
            qt_buttons[qt_button] = label
        cancel_button = None
        if cancel_allowed:
            cancel_button = msg_box.addButton(QMessageBox.StandardButton.Cancel)
        msg_box.exec()
        clicked_button = msg_box.clickedButton()
        ok = clicked_button in qt_buttons
        cancel = cancel_allowed and clicked_button == cancel_button
        ans = qt_buttons.get(clicked_button)
    else:
        options = "/".join(button_labels)
        if cancel_allowed:
            options += "/cancel"
        prompt_text = f"{prompt} ({options}): "
        # Use input() for terminal interaction
        ans_text = input(prompt_text).strip().lower()
        alias_map = {label: label_map[label] for label in normalized_labels}
        first_char_counts = {}
        for label in normalized_labels:
            first_char = label[:1]
            first_char_counts[first_char] = first_char_counts.get(first_char, 0) + 1
        for label in normalized_labels:
            first_char = label[:1]
            if first_char_counts.get(first_char, 0) == 1:
                alias_map[first_char] = label_map[label]
            if label == "yes":
                alias_map["y"] = label_map[label]
            if label == "no":
                alias_map["n"] = label_map[label]

        ok = ans_text in alias_map
        cancel = ans_text in ["cancel", "c"]
        ans = alias_map.get(ans_text)
    if cancel and cancel_allowed:
        if close_on_cancel:
            logging.info("User canceled, closing app.")
            sys.exit(0)
        else:
            logging.info("User cancelled the operation.")
            return None
    if not ok or ans is None:
        if len(button_labels) == 2:
            warning_message = (
                "You need to provide an appropriate input to proceed "
                f"({first_label} or {second_label})!"
            )
        else:
            warning_message = (
                "You need to provide an appropriate input to proceed "
                f"({', '.join(button_labels)})!"
            )
    else:
        warning_message = None
    if warning_message is not None:
        if gui_mode:
            parent = main_widget()
            QMessageBox().warning(parent, "Warning", warning_message)
        else:
            logging.warning(warning_message)
        return ask_user_custom(
            prompt,
            buttons=button_labels,
            cancel_allowed=cancel_allowed,
            close_on_cancel=close_on_cancel,
            parent=parent,
        )
    if len(button_labels) == 2:
        return ans == first_label
    return ans


def get_user_input(
    prompt,
    input_type="string",
    file_filter=None,
    cancel_allowed=True,
    exit_on_cancel=False,
    parent=None,
):
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
    cancel_allowed : bool, optional
        If True, allows the user to cancel the input operation. Defaults to True.
    exit_on_cancel : bool, optional
        If True, the app exits after cancel. Defaults to False.
    parent : QWidget | None, optional
        Set the parent of the modal widget.

    Returns
    -------
    user_input : str | PathLike | None
        The user input as a string/PathLike depending on input_Type, or None if cancelled or unavailable.

    Raises
    ------
    RuntimeError
        If input is not available in the current environment.
    ValueError
        If `input_type` is not "string" or "path".
    """
    type_error_message = (
        f"input_type must be 'string', 'folder' or 'file', not '{input_type}'"
    )
    if gui_mode:
        parent = parent or main_widget()
        if input_type == "string":
            user_input, ok = QInputDialog.getText(parent, "Input String!", prompt)
        elif input_type == "folder":
            user_input = compat.getexistingdirectory(parent, prompt)
            ok = user_input != ""
        elif input_type == "file":
            user_input, ok = compat.getopenfilename(parent, prompt, filters=file_filter)
        else:
            raise ValueError(type_error_message)
    else:
        if input_type == "string":
            user_input = input(f"{prompt}: ")
        elif input_type == "folder":
            ans = input("Do you want to use the current directory? (y/n/c/cancel): ")
            if ans.lower() in ["y", "yes"]:
                user_input = os.getcwd()
            elif ans.lower() in ["c", "cancel"]:
                user_input = None
            else:
                user_input = input(f"{prompt}: ")
        elif input_type == "file":
            user_input = input(
                f"{prompt} | Please enter the full path to the file (c/cancel): "
            )
        else:
            raise ValueError(type_error_message)
        ok = user_input.lower() not in ["cancel", "c"]
    if cancel_allowed and not ok:
        if exit_on_cancel:
            logging.info("User canceled, closing app.")
            sys.exit(0)
        else:
            logging.debug("User cancelled the input operation.")
            return None
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
        raise_user_attention(warning_message, message_type="warning")
        return get_user_input(prompt, input_type)

    # Convert path-strings to Path-objects
    if input_type in ["folder", "file"] and user_input is not None:
        user_input = Path(user_input)

    return user_input


def raise_user_attention(message, message_type="warning", parent=None):
    """Raise a message to the user, either as a warning or an error."""
    if gui_mode:
        parent = parent or main_widget()
        if message_type == "warning":
            QMessageBox().warning(parent, "Warning", message)
        elif message_type == "error":
            QMessageBox().critical(parent, "Error", message)
        elif message_type == "info":
            QMessageBox().information(parent, "Information", message)
        else:
            raise ValueError(f"Unknown message type: {message_type}")
    if message_type == "warning":
        logging.warning(message)
    elif message_type == "error":
        logging.error(message)
    elif message_type == "info":
        logging.info(message)
    else:
        raise ValueError(f"Unknown message type: {message_type}")


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


def mouseDragBetween(
    widget_from,
    pos_from,
    widget_to,
    pos_to,
    button=Qt.MouseButton.LeftButton,
    modifier=None,
):
    """Drag from one widget to another using low-level mouse events.

    Sends MousePress on source, several MouseMove events with button
    held to trigger startDrag, then moves into target and releases.
    """
    if modifier is None:
        modifier = Qt.KeyboardModifier.NoModifier
    QTest.qWaitForWindowExposed(widget_from.window())
    QTest.qWaitForWindowExposed(widget_to.window())
    # Press on source
    mousePress(widget=widget_from, pos=pos_from, button=button, modifier=modifier)
    # Move within source to exceed drag threshold
    mouseMove(
        widget=widget_from,
        pos=QPoint(pos_from.x() + 30, pos_from.y()),
        button=button,
        modifier=modifier,
    )
    QTest.qWait(10)
    # Move into target widget while holding button
    mouseMove(widget=widget_to, pos=pos_to, button=button, modifier=modifier)
    QTest.qWait(10)
    mouseRelease(widget=widget_to, pos=pos_to, button=button, modifier=modifier)


########################################################################################
# Theme & Colors
########################################################################################
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
    style = Settings().get("app_style")
    app.setStyle(style)
    app_theme = Settings().get("app_theme")
    # Detect system theme
    if app_theme == "auto":
        app_theme = _get_auto_theme()
    app.setPalette(get_palette(app_theme))
    # Set Icon
    if app_theme == "light":
        icon_name = "mne_pipeline_icon_light.png"
    else:
        icon_name = "mne_pipeline_icon_dark.png"
    icon_path = join(str(resources.files(extra)), icon_name)
    app_icon = QIcon(str(icon_path))
    app.setWindowIcon(app_icon)


def set_app_font_size(font_size=None):
    app = QApplication.instance()
    font_size = font_size or Settings().get("app_font_size")
    font = QFont()
    font.setFamilies(["Segoe UI", "Noto Sans", "Open Sans", "DejaVu Sans"])
    font.setPointSize(font_size)
    app.setFont(font)


class ColorTester(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        _widgets["color_tester"] = self
        theme = Settings().get("app_theme")
        if theme == "auto":
            theme = _get_auto_theme()
        self.theme = theme
        self.color_display = {}
        self.init_ui()
        self.theme_color_path = join(str(resources.files(extra)), "color_themes.json")

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


def edit_font(widget: QWidget, font_size: int, bold: bool = False) -> None:
    font = widget.font()
    font.setPointSize(font_size)
    font.setBold(bold)
    widget.setFont(font)
