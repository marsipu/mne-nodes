"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import mne
from qtpy.QtCore import QProcess, Signal, Qt
from qtpy.QtGui import QAction, QKeySequence
from qtpy.QtWidgets import QApplication, QMainWindow, QMessageBox

from mne_nodes import _widgets, iswin
from mne_nodes.gui.console import ConsoleDock
from mne_nodes.gui.dialogs import SysInfoMsg
from mne_nodes.gui.gui_utils import center, set_ratio_geometry
from mne_nodes.gui.node.node_picker import NodePicker
from mne_nodes.gui.node.node_viewer import NodeViewer
from mne_nodes.pipeline.execution import ProcessDialog
from mne_nodes.pipeline.pipeline_utils import restart_program, _run_from_script


class MainWindow(QMainWindow):
    """The main Windows containing the node-viewer and the console-widget.

    It also provides a menubar, toolbar and a statusbar.
    Parameters
    ----------
    controller : Controller
        The controller managing the pipeline.
    """

    processFinished = Signal(int, int, QProcess.ExitStatus)

    def __init__(self, controller):
        super().__init__()
        _widgets["main_window"] = self
        self._controller = controller
        self.settings = controller.settings

        # Initialize properties
        # Console/Error management moved into ConsoleDock

        # Set geometry to ratio of screen-geometry
        set_ratio_geometry(self.settings.get("screen_ratio"), self)
        center(self)

        # Init Dock options
        self.setDockOptions(QMainWindow.DockOption.AnimatedDocks)

        # Init Node-Viewer
        self.viewer = NodeViewer(controller, self)
        self.setCentralWidget(self.viewer)
        self.viewer.load_config(controller.node_config)

        # Init Console-Widget (manages per-process consoles & errors)
        self.console_dock = ConsoleDock(controller, self)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.console_dock)
        self.console_dock.hide()

        # Init Node-Picker dock
        self.node_picker = NodePicker(controller, self)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.node_picker)

        # Init QActions
        self.actions = {}
        load_help = "Load another project with a new configuration file."
        self.actions["load"] = QAction(
            "&Load Configuration",
            parent=self,
            toolTip="Load Configuration",
            statusTip=load_help,
            whatsThis=load_help,
            shortcut=QKeySequence("Ctrl+O"),
        )
        self.actions["save"] = QAction("&Save Configuration", parent=self)
        self.actions["exit"] = QAction("&Exit", parent=self)
        # Viewer actions
        autolayout_help = "Automatically arrange all nodes in the viewer."
        self.actions["autolayout"] = QAction(
            "&Auto-Layout Nodes",
            parent=self,
            toolTip="Auto-Layout Nodes",
            statusTip=autolayout_help,
            whatsThis=autolayout_help,
            shortcut=QKeySequence("Ctrl+L"),
        )
        self.actions["autolayout"].triggered.connect(self.viewer.auto_layout_nodes)

        # ToDo: Init Menu
        # ToDo: Init Toolbar
        self.toolbar = self.addToolBar("Main Toolbar")
        self.toolbar.addAction(self.actions["autolayout"])
        # ToDo: Init Infobar

        # Show the main window
        self.show()

        # Initialize on last opened screen
        screen_name = self.settings.get("screen_name")
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
        if hasattr(self, "node_picker") and self.node_picker is not None:
            self.node_picker.ct = controller

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
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
            # Register with controller for central tracking
            ProcessDialog(
                self,
                command,
                show_buttons=True,
                show_console=True,
                close_directly=True,
                title="Updating Pipeline...",
                blocking=True,
                controller=self.controller,
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
        ProcessDialog(
            self,
            command,
            show_buttons=True,
            show_console=True,
            close_directly=True,
            title="Updating MNE-Python...",
            blocking=True,
            controller=self.controller,
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

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_C:
            self.console_dock.setVisible(not self.console_dock.isVisible())
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        # Persist screen info
        self.settings.set("screen_name", self.screen().name())
        _widgets["main_window"] = None
        self.controller.save_node_config(self.viewer.to_dict())
        event.accept()
