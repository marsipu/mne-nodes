"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

import qtpy
from qtpy.QtCore import QTimer, Qt
from qtpy.QtWidgets import QApplication

import mne_nodes
from mne_nodes.gui.console import StdoutStderrStream
from mne_nodes.gui.gui_utils import set_app_font_size, set_app_theme
from mne_nodes.gui.main_window import MainWindow
from mne_nodes.pipeline.controller import Controller
from mne_nodes.pipeline.exception_handling import UncaughtHook
from mne_nodes.pipeline.legacy import legacy_import_check
from mne_nodes.pipeline.settings import Settings

app_name = "mne-nodes"
organization_name = "marsipu"
domain_name = "https://github.com/marsipu/mne-nodes"


def init_streams() -> None:
    # Redirect stdout and stderr to capture it later in GUI
    sys.stdout = StdoutStderrStream("stdout")
    sys.stderr = StdoutStderrStream("stderr")


def init_logging(debug_mode: bool = False) -> None:
    """Initialize Root Logger."""
    logger = logging.getLogger()
    if debug_mode:
        logger.setLevel(logging.DEBUG)
        fmt = "{asctime} [{levelname}] {module}.{funcName}: {message}"
    else:
        logger.setLevel(Settings().value("log_level", defaultValue=logging.INFO))
        fmt = "[{levelname}] {message}"
    # Format console handler
    date_fmt = "%H:%M:%S"
    formatter = logging.Formatter(fmt, date_fmt, style="{")
    console_handler = logging.StreamHandler()
    console_handler.set_name("console")
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    # Format file handler
    logging_path = Settings().value("log_file_path") or Path.home() / "mne_nodes.log"
    file_handler = logging.FileHandler(logging_path, mode="w", encoding="utf-8")
    file_handler.set_name("file")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)


def main() -> None:
    # ToDo: Change Debug mode initialization (command-line, enviroment-variable, settings)
    init_logging(mne_nodes.debug_mode)

    logging.info("Starting MNE-Nodes...")

    if mne_nodes.gui_mode:
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
        if mne_nodes.debug_mode:
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
    else:
        # Headless mode (no gui)
        logging.info("Started in headless mode (no gui).")
        # ToDo: Implement headless functionality


if __name__ == "__main__":
    # Check for changes in required packages
    legacy_import_check()

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
