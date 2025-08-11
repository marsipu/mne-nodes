"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import mne
from qtpy.QtCore import Qt
from qtpy.QtWidgets import QApplication, QMainWindow, QMessageBox

from mne_nodes import _object_refs, iswin
from mne_nodes.gui.console import ConsoleDock
from mne_nodes.gui.dialogs import SysInfoMsg
from mne_nodes.gui.gui_utils import center, set_ratio_geometry
from mne_nodes.gui.node.node_viewer import NodeViewer
from mne_nodes.pipeline.execution import QProcessDialog
from mne_nodes.pipeline.pipeline_utils import restart_program, _run_from_script


class MainWindow(QMainWindow):
    """The main Windows containing the node-viewer and the console-widget.

    It also provides a menubar, toolbar and a statusbar.
    """

    def __init__(self, controller):
        super().__init__()
        _object_refs["main_window"] = self
        self._controller = controller
        self.settings = controller.settings

        # Initialize on last opened screen
        screen_name = self.settings.value("screen_name")
        if screen_name is not None:
            for screen in QApplication.screens():
                if screen.name() == screen_name:
                    self.windowHandle().setScreen(screen)
                    break

        # Set geometry to ratio of screen-geometry
        set_ratio_geometry(self.settings.value("screen_ratio"), self)
        center(self)

        # Init Node-Viewer
        self.viewer = NodeViewer(controller, self)
        self.setCentralWidget(self.viewer)
        self.viewer.reload_config()

        # Init Console-Widget
        self.console = ConsoleDock(controller, self)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.console)

        # Todo: Init Node-Palette
        # ToDo: Init Menu
        # ToDo: Init Toolbar
        # ToDo: Init Infobar

        # Show the main window
        self.show()
        self.statusBar().showMessage(f"{self.controller.name} is ready.")

    @property
    def controller(self):
        """Get the controller."""
        return self._controller

    @controller.setter
    def controller(self, controller):
        """Set the controller and update the main window."""
        self._controller = controller
        self.setWindowTitle(f"MNE-Nodes - {self._controller.name}")
        self.viewer.ct = controller
        self.console.ct = controller

    def start_process(self, command):
        QProcessDialog(
            self,
            command,
            show_buttons=True,
            show_console=True,
            close_directly=False,
            title="Starting Process...",
            blocking=True,
        )

    def restart(self):
        self.close()
        restart_program()

    def update_pipeline(self, version):
        if version == "stable":
            command = "pip install --upgrade mne_nodes"
        else:
            command = "pip install https://github.com/marsipu/mne-nodes/zipball/main"
        if iswin and not _run_from_script():
            QMessageBox.information(
                self,
                "Manual install required!",
                f"To update you need to exit the program "
                f'and type "{command}" into the terminal!',
            )
        else:
            QProcessDialog(
                self,
                command,
                show_buttons=True,
                show_console=True,
                close_directly=True,
                title="Updating Pipeline...",
                blocking=True,
            )

            answer = QMessageBox.question(
                self,
                "Do you want to restart?",
                "Please restart the Pipeline-Program "
                "to apply the changes from the Update!",
            )

            if answer == QMessageBox.Yes:
                self.restart()

    def update_mne(self):
        command = "pip install --upgrade mne"
        QProcessDialog(
            self,
            command,
            show_buttons=True,
            show_console=True,
            close_directly=True,
            title="Updating MNE-Python...",
            blocking=True,
        )

        answer = QMessageBox.question(
            self,
            "Do you want to restart?",
            "Please restart the Pipeline-Program to apply the changes from the Update!",
        )

        if answer == QMessageBox.Yes:
            self.restart()

    def show_sys_info(self):
        SysInfoMsg(self)
        mne.sys_info()

    def closeEvent(self, event):
        self.settings.setValue("screen_name", self.screen().name())
        event.accept()
