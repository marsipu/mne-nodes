"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import argparse
import logging
import sys

import qtpy
from qtpy.QtCore import QTimer, Qt
from qtpy.QtWidgets import QApplication

import mne_nodes
from mne_nodes.gui.gui_utils import set_app_font_size, set_app_theme
from mne_nodes.gui.main_window import MainWindow
from mne_nodes.pipeline.controller import Controller
from mne_nodes.pipeline.exception_handling import UncaughtHook
from mne_nodes.pipeline.streams import init_streams, init_logging

app_name = "mne-nodes"
organization_name = "marsipu"
domain_name = "https://github.com/marsipu/mne-nodes"


def main() -> None:
    # ToDo: Change Debug mode initialization (command-line, enviroment-variable, settings)
    init_logging(mne_nodes.debug_mode())
    logging.info("Starting MNE-Nodes...")
    # Set gui_mode to true since starting as module always means gui-mode
    mne_nodes.gui_mode = True
    # Create QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    app.setApplicationName(app_name)
    app.setOrganizationName(organization_name)
    app.setOrganizationDomain(domain_name)
    # For Spyder to make console accessible again
    app.lastWindowClosed.connect(app.quit)

    # Avoid file-dialog-problems with custom file-managers in linux
    if mne_nodes.islin:
        app.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs, True)

    # Initialize streams from stdout/stderr into Qt
    init_streams()

    # Show Qt-binding
    logging.info(f"Using {qtpy.API_NAME} {qtpy.QT_VERSION}")

    # Initialize Exception-Hook
    if mne_nodes.debug_mode():
        logging.info("Debug-Mode is activated")
    else:
        qt_exception_hook = UncaughtHook()
        sys.excepthook = qt_exception_hook.exception_hook

    # Set style and font
    set_app_theme()
    set_app_font_size()

    # Initialize controller and main window
    controller = Controller()
    MainWindow(controller)

    # Command-Line interrupt with Ctrl+C possible
    timer = QTimer()
    timer.timeout.connect(lambda: None)
    timer.start(500)

    sys.exit(app.exec())


if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        prog="MNE-Nodes", description="A GUI with Nodes for MNE-Python"
    )
    parser.add_argument(
        "--nogui", "-n", action="store_true", help="Run headless without GUI"
    )
    cli_args = parser.parse_args(sys.argv[1:])

    if cli_args.nogui:
        mne_nodes.gui_mode = False

    main()
