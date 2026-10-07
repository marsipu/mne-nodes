"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

from qtpy.QtWidgets import QDialog, QFileDialog, QInputDialog, QMessageBox

from mne_nodes import gui_mode
from mne_nodes.logger import logger


def question_yes_no(prompt, cancel_allowed=True, parent=None):
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle("Question")
    box.setText(prompt)
    if cancel_allowed:
        buttons = (
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
            | QMessageBox.StandardButton.Cancel
        )
    else:
        buttons = QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    box.setStandardButtons(buttons)
    box.exec()
    ans = box.result() == QMessageBox.StandardButton.Yes
    cancel = box.result() == QMessageBox.StandardButton.Cancel
    return ans, cancel


def information_message(message, parent=None):
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Information)
    box.setWindowTitle("Information")
    box.setText(message)
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    box.exec()


def warning_message(message, parent=None):
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle("Warning")
    box.setText(message)
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    box.exec()


def error_message(message, parent=None):
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Critical)
    box.setWindowTitle("Error")
    box.setText(message)
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    box.exec()


def ask_user(prompt, cancel_allowed=True, close_on_cancel=False, parent=None):
    """Ask the user a yes or no question.

    The answer is returned as a boolean. If the user cancels the
    operation, None is returned.

    Parameters
    ----------
    prompt : str
        The prompt message to display to the user.
    cancel_allowed : bool
        If True, allows the user to cancel the operation. Defaults to True.
    close_on_cancel : bool
        If True, the app exits after cancel. Defaults to False.
    parent : QWidget | None, optional
        Set the parent of the modal widget.
    """
    if gui_mode:
        ans, cancel = question_yes_no(
            prompt, cancel_allowed=cancel_allowed, parent=parent
        )
        ok = True
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
            logger.info("User canceled, closing app.")
            sys.exit(0)
        else:
            logger.info("User cancelled the operation.")
            return None
    if not ok or ans is None:
        message = "You need to provide an appropriate input to proceed (yes/n or no/n)!"
    else:
        message = None
    if message is not None:
        if gui_mode:
            warning_message(message, parent=parent)
        else:
            logger.warning(message)
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
            logger.info("User canceled, closing app.")
            sys.exit(0)
        else:
            logger.info("User cancelled the operation.")
            return None
    if not ok or ans is None:
        if len(button_labels) == 2:
            message = (
                "You need to provide an appropriate input to proceed "
                f"({first_label} or {second_label})!"
            )
        else:
            message = (
                "You need to provide an appropriate input to proceed "
                f"({', '.join(button_labels)})!"
            )
    else:
        message = None
    if message is not None:
        if gui_mode:
            warning_message(message, parent=parent)
        else:
            logger.warning(message)
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


def _get_text_input(prompt, parent=None, title="Input String!"):
    dialog = QInputDialog(parent)
    dialog.setInputMode(QInputDialog.InputMode.TextInput)
    dialog.setWindowTitle(title)
    dialog.setLabelText(prompt)

    ok = dialog.exec() == QDialog.DialogCode.Accepted
    text = dialog.textValue() if ok else ""
    return text, ok


def _get_existing_directory(prompt, parent=None):
    dialog = QFileDialog(parent, prompt)
    dialog.setFileMode(QFileDialog.FileMode.Directory)
    dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)

    ok = dialog.exec() == QDialog.DialogCode.Accepted
    if not ok:
        return "", False

    selected = dialog.selectedFiles()
    return (selected[0] if selected else ""), True


def _get_open_file(prompt, parent=None, file_filter=None):
    dialog = QFileDialog(parent, prompt)
    dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
    if file_filter:
        dialog.setNameFilter(file_filter)

    ok = dialog.exec() == QDialog.DialogCode.Accepted
    if not ok:
        return "", False

    selected = dialog.selectedFiles()
    return (selected[0] if selected else ""), True


def _get_save_file(prompt, parent=None, file_filter=None):
    dialog = QFileDialog(parent, prompt)
    dialog.setFileMode(QFileDialog.FileMode.AnyFile)
    dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
    if file_filter:
        dialog.setNameFilter(file_filter)

    ok = dialog.exec() == QDialog.DialogCode.Accepted
    if not ok:
        return "", False

    selected = dialog.selectedFiles()
    return (selected[0] if selected else ""), True


def get_user_input(
    prompt,
    input_type="string",
    file_filter=None,
    cancel_allowed=True,
    exit_on_cancel=False,
    parent=None,
) -> str | os.PathLike | None:
    """Get user input either via GUI or terminal, supporting string and path
    input.

    Parameters
    ----------
    prompt : str
        The prompt message to display to the user.
    input_type : str, optional
        The type of input to request: "string", "url", "folder", "file" or
        "file_new".
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
        If `input_type` is not a supported input type.
    """
    type_error_message = f"input_type must be 'string', 'url', 'folder', 'file', 'file_new', not '{input_type}'"
    if gui_mode:
        if input_type in ("string", "url"):
            user_input, ok = _get_text_input(prompt, parent=parent)
        elif input_type == "folder":
            user_input, ok = _get_existing_directory(prompt, parent=parent)
        elif input_type == "file":
            user_input, ok = _get_open_file(
                prompt, parent=parent, file_filter=file_filter
            )
        elif input_type == "file_new":
            user_input, ok = _get_save_file(
                prompt, parent=parent, file_filter=file_filter
            )
        else:
            raise ValueError(type_error_message)
    else:
        if input_type in ("string", "url"):
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
        elif input_type == "file_new":
            user_input = input(
                f"{prompt} | Please enter the full path for the new file (c/cancel): "
            )
        else:
            raise ValueError(type_error_message)
        ok = user_input is not None and user_input.lower() not in ["cancel", "c"]
    if cancel_allowed and not ok:
        if exit_on_cancel:
            logger.info("User canceled, closing app.")
            sys.exit(0)
        else:
            logger.debug("User cancelled the input operation.")
            return None
    # Check user input
    if not ok or user_input is None:
        warning_message = "You need to provide an appropriate input to proceed!"
    elif input_type == "folder" and not os.path.isdir(user_input):
        warning_message = "The provided path is not a valid directory!"
    elif input_type == "file" and not os.path.isfile(user_input):
        warning_message = "The provided path does not exist!"
    elif input_type in ("string", "url") and not isinstance(user_input, str):
        warning_message = "The provided input is not a valid string!"
    elif input_type == "url":
        user_input = user_input.strip().replace("\\", "/")
        url_parts = urlsplit(user_input)
        if url_parts.scheme not in {"http", "https"} or not url_parts.netloc:
            warning_message = "The provided input is not a valid URL!"
        else:
            warning_message = None
    else:
        warning_message = None
    if warning_message is not None:
        raise_user_attention(warning_message, message_type="warning")
        return get_user_input(
            prompt,
            input_type=input_type,
            file_filter=file_filter,
            cancel_allowed=cancel_allowed,
            exit_on_cancel=exit_on_cancel,
            parent=parent,
        )

    # Convert path-strings to Path-objects
    if input_type in ["folder", "file", "file_new"] and user_input is not None:
        user_input = Path(user_input)

    return user_input


def raise_user_attention(message, message_type="warning", parent=None):
    """Raise a message to the user, either as a warning or an error."""
    if gui_mode:
        if message_type == "warning":
            warning_message(message, parent=parent)
        elif message_type == "error":
            error_message(message, parent=parent)
        elif message_type == "info":
            information_message(message, parent=parent)
        else:
            raise ValueError(f"Unknown message type: {message_type}")
    if message_type == "warning":
        logger.warning(message)
    elif message_type == "error":
        logger.error(message)
    elif message_type == "info":
        logger.info(message)
    else:
        raise ValueError(f"Unknown message type: {message_type}")
