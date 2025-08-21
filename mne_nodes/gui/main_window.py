"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import sys

import mne

from qtpy.QtCore import Qt, QProcess
from qtpy.QtWidgets import QApplication, QMainWindow, QMessageBox

from mne_nodes import _object_refs, iswin
from mne_nodes.gui.console import ConsoleDock
from mne_nodes.gui.dialogs import SysInfoMsg
from mne_nodes.gui.gui_utils import center, set_ratio_geometry
from mne_nodes.gui.node.node_viewer import NodeViewer
from mne_nodes.gui.node.node_picker import NodePicker
from mne_nodes.pipeline.execution import QProcessDialog
from mne_nodes.pipeline.pipeline_utils import restart_program, _run_from_script


class MainWindow(QMainWindow):
    """The main Windows containing the node-viewer and the console-widget.

    It also provides a menubar, toolbar and a statusbar.
    """

    def __init__(self, controller, viewer=None):
        super().__init__()
        _object_refs["main_window"] = self
        self._controller = controller
        self.settings = controller.settings

        # Initialize properties
        self.qprocesses = {}
        # Console/Error management moved into ConsoleDock

        # Set geometry to ratio of screen-geometry
        set_ratio_geometry(self.settings.value("screen_ratio"), self)
        center(self)

        # Init Dock options
        # ToDo: Fix floatable dock not working as expected with node-viewer as central widget.
        self.setDockOptions(
            QMainWindow.DockOption.AnimatedDocks
            | QMainWindow.DockOption.AllowNestedDocks
            | QMainWindow.DockOption.AllowTabbedDocks
        )

        # Init Node-Viewer
        self.viewer = viewer or NodeViewer(controller, self)
        self.setCentralWidget(self.viewer)
        self.viewer.load_config(controller.node_config)

        # Init Console-Widget (manages per-process consoles & errors)
        self.console_dock = ConsoleDock(controller, self)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.console_dock)
        self.console_dock.hide()

        # Init Node-Picker dock
        self.node_picker = NodePicker(controller, self)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.node_picker)

        # ToDo: Init Menu
        # ToDo: Init Toolbar
        # ToDo: Init Infobar

        # Show the main window
        self.show()

        # Initialize on last opened screen
        screen_name = self.settings.value("screen_name")
        if screen_name is not None:
            for screen in QApplication.screens():
                if screen.name() == screen_name:
                    self.windowHandle().setScreen(screen)
                    break

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
        self.console_dock.ct = controller
        # Also update picker/controller link if present
        if hasattr(self, "node_picker") and self.node_picker is not None:
            self.node_picker.ct = controller

    def _change_process_state(self, process_idx, state):
        """Handle changes in the process state."""
        if state == QProcess.ProcessState.NotRunning:
            self.controller.process(process_idx)["state"] = "finished"
        elif state == QProcess.ProcessState.Starting:
            self.controller.process(process_idx)["state"] = "starting"
        elif state == QProcess.ProcessState.Running:
            self.controller.process(process_idx)["state"] = "running"
        else:
            raise RuntimeError(
                f"Unknown process state: {state} for process {process_idx}"
            )

    def _handle_stdout(self, process_idx):
        process = self.qprocesses[process_idx]
        data = bytes(process.readAllStandardOutput())
        # Forward to ConsoleDock-managed console
        self.console_dock.push_stdout(process_idx, data)

    def _handle_stderr(self, process_idx):
        process = self.qprocesses[process_idx]
        data = bytes(process.readAllStandardError())
        # Forward to ConsoleDock-managed console and track error
        self.console_dock.push_stderr(process_idx, data)

    def _process_finished(self, process_idx, code, status):
        print(f"Process {process_idx} finished with code {code} and status {status}")
        self.console_dock.process_finished(process_idx)

    def start_process(self, process_idx):
        # Prepare per-process UI in the dock
        self.console_dock.add_process(process_idx)
        # Prepare process
        process = QProcess(self)
        self.qprocesses[process_idx] = process
        process.setProgram(sys.executable)
        process.setWorkingDirectory(self.controller.config["data_path"])
        process.stateChanged.connect(
            lambda state: self._change_process_state(process_idx, state)
        )
        process.readyReadStandardOutput.connect(
            lambda: self._handle_stdout(process_idx)
        )
        process.readyReadStandardError.connect(lambda: self._handle_stderr(process_idx))
        process.finished.connect(
            lambda code, status: self._process_finished(process_idx, code, status)
        )
        file_path = self.controller.process(process_idx)["file"]
        process.setArguments([str(file_path)])
        process.start()

    def restart(self):
        self.close()
        restart_program()

    def update_app(self, version):
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

            if answer == QMessageBox.StandardButton.Yes:
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

        if answer == QMessageBox.StandardButton.Yes:
            self.restart()

    def show_sys_info(self):
        SysInfoMsg(self)
        mne.sys_info()

    def keyPressEvent(self, event):
        """Handle key press events."""
        if event.key() == Qt.Key.Key_C:
            # Toggle visibility of the console dock
            self.console_dock.setVisible(not self.console_dock.isVisible())
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        # Persist screen info
        self.settings.setValue("screen_name", self.screen().name())
        # Stop any running processes and workers
        for idx, proc in list(self.qprocesses.items()):
            proc.finished.disconnect()
            proc.readyReadStandardOutput.disconnect()
            proc.readyReadStandardError.disconnect()
            if proc.state() != QProcess.ProcessState.NotRunning:
                proc.kill()
                proc.waitForFinished(2000)
        # Stop and clear console workers
        self.console_dock.stop_all()
        self.qprocesses.clear()
        # Clear global reference for tests/GC
        _object_refs["main_window"] = None
        # Save node configuration
        self.controller.save_node_config(self.viewer.to_dict())
        # Close the main window
        event.accept()
