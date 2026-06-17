"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import mne
from qtpy.QtCore import QProcess, Signal, Qt
from qtpy.QtGui import QAction, QKeySequence
from qtpy.QtWidgets import QApplication, QMainWindow

from mne_nodes import _widgets, iswin
from mne_nodes.gui.console import ConsoleDock
from mne_nodes.gui.dialogs import SysInfoMsg
from mne_nodes.gui.gui_utils import (
    ask_user,
    center,
    get_user_input,
    information_message,
    set_ratio_geometry,
)
from mne_nodes.gui.node.node_viewer import NodeViewer
from mne_nodes.gui.run_widgets import ProcessDialog, WorkerDialog
from mne_nodes.pipeline.data_import import load_sample_bids
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
        self.viewer.load_config(controller.get("node_config"))

        # Init Console-Widget (manages per-process consoles & errors)
        self.console_dock = ConsoleDock(controller, self)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.console_dock)
        self.console_dock.hide()

        # Pipeline Actions
        import_pipeline_action = QAction(
            "&Import Pipeline",
            parent=self,
            statusTip="Import a Pipeline from a JSON file",
        )
        import_pipeline_action.triggered.connect(self.controller.import_pipeline)
        export_pipeline_action = QAction(
            "&Export Pipeline", parent=self, statusTip="Export Pipeline to a JSON file"
        )
        export_pipeline_action.triggered.connect(self.controller.export_pipeline)
        # BIDS Actions
        sample_action = QAction(
            "&Add Sample BIDS Data", parent=self, statusTip="Add Sample BIDS Data"
        )
        sample_action.triggered.connect(self.add_sample_bids)
        change_bids_root_action = QAction(
            "&Change BIDS Root",
            parent=self,
            statusTip="Change the BIDS root directory for the current project.",
        )
        load_action = QAction(
            "&Load Configuration",
            parent=self,
            statusTip="Load another project with a new configuration file.",
            shortcut=QKeySequence("Ctrl+O"),
        )
        load_action.triggered.connect(self.load_config)
        exit_action = QAction("&Exit", parent=self)
        exit_action.triggered.connect(self.close)
        # Viewer actions
        autolayout_action = QAction(
            "&Auto-Layout Nodes",
            parent=self,
            statusTip="Automatically arrange all nodes in the viewer.",
            shortcut=QKeySequence("Ctrl+L"),
        )
        autolayout_action.triggered.connect(self.viewer.auto_layout_nodes)

        # Menu
        pipeline_menu = self.menuBar().addMenu("&Pipeline")
        pipeline_menu.addAction(import_pipeline_action)
        pipeline_menu.addAction(export_pipeline_action)
        bids_menu = self.menuBar().addMenu("&BIDS")
        bids_menu.addAction(sample_action)
        bids_menu.addAction(change_bids_root_action)
        bids_menu.addSeparator()
        bids_menu.addAction(exit_action)
        config_menu = self.menuBar().addMenu("&Config")
        config_menu.addAction(load_action)
        # Toolbar
        self.toolbar = self.addToolBar("Main Toolbar")
        self.toolbar.addAction(autolayout_action)

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

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def load_config(self):
        # Initialize new config-path by setting it to None
        self.controller.config_path = None

    def add_sample_bids(self):
        sample_root = get_user_input(
            "Enter the BIDS root directory for the sample data:", "folder", parent=self
        )
        if sample_root is not None:
            WorkerDialog(
                self,
                function=load_sample_bids,
                title="Loading Sample BIDS Data",
                show_console=True,
                blocking=True,
                bids_root=sample_root,
            )
            self.controller.bids_root = sample_root

    def change_bids_root(self):
        self.controller.bids_root = None

    def restart(self):
        self.close()
        restart_program()

    def update_app(self, version):
        if version == "stable":
            command = "pip install --upgrade mne_nodes"
        else:
            command = "pip install https://github.com/marsipu/mne-nodes/zipball/main"
        if iswin and not _run_from_script():
            information_message(
                f"Manual install required! To update you need to exit the program and type '{command}' into the terminal!",
                parent=self,
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
            )

            ans = ask_user(
                "Do you want to restart? Please restart the Pipeline-Program to apply the changes from the Update!",
                parent=self,
            )
            if ans:
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
        )

        ans = ask_user(
            "Do you want to restart? Please restart the Pipeline-Program to apply the changes from the Update!",
            parent=self,
        )
        if ans:
            self.restart()

    def show_sys_info(self):
        SysInfoMsg(self).show()
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
        self.controller.set("node_config", self.viewer.to_dict())
        self.controller.flush()
        event.accept()
