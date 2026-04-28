import sys

from qtpy.QtWidgets import QApplication

from mne_nodes.gui.gui_utils import (
    ask_user,
    ask_user_custom,
    get_user_input,
    raise_user_attention,
)

app = QApplication(sys.argv)

ask_user("This is a test question. Do you want to proceed?")
ask_user_custom(
    "This is a custom question. Please choose an option.",
    buttons=["Option 1", "Option 2", "Option 3"],
)
get_user_input("Please enter your name:")
get_user_input("Please select a folder:", input_type="folder")
get_user_input("Please select a file:", input_type="file")
raise_user_attention("This is some information for you.", message_type="info")
raise_user_attention(
    "This is an important message that requires your attention!", message_type="warning"
)
raise_user_attention(
    "An error has occurred. Please check your input.", message_type="error"
)

sys.exit(app.exec())
