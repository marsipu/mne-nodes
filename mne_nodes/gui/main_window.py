"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import sys

import mne
from qtpy.QtCore import QProcess, Qt, Signal
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
from mne_nodes.gui.node.node_picker import NodePicker
from mne_nodes.gui.node.node_viewer import NodeViewer
from mne_nodes.gui.run_widgets import ProcessDialog, WorkerDialog
from mne_nodes.pipeline.data_import import load_sample_bids
from mne_nodes.pipeline.pipeline_utils import _run_from_script, restart_program


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
        self.node_picker = None

        # Initialize properties
        # Console/Error management moved into ConsoleDock

        # Set geometry to ratio of screen-geometry
        set_ratio_geometry(self.settings.get("screen_ratio"), self)
        center(self)

        # Init Dock options
        self.setDockOptions(QMainWindow.DockOption.AnimatedDocks)

        # Init Node-Viewer without loading project state yet; the controller may
        # still need to finish first-run setup and welcome-tour prompting.
        self.viewer = NodeViewer(controller, self)
        self.setCentralWidget(self.viewer)

        # Init Console-Widget (manages per-process consoles & errors)
        self.console_dock = ConsoleDock(controller, self)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.console_dock)
        self.console_dock.hide()

        # File Actions
        new_config_action = QAction(
            "&New Pipeline",
            parent=self,
            statusTip="Create a new pipeline file.",
            shortcut=QKeySequence("Ctrl+N"),
        )
        new_config_action.triggered.connect(self.new_pipeline)
        load_config_action = QAction(
            "&Load Pipeline",
            parent=self,
            statusTip="Load another pipeline file.",
            shortcut=QKeySequence("Ctrl+O"),
        )
        load_config_action.triggered.connect(self.load_pipeline)
        save_config_action = QAction(
            "&Save Pipeline",
            parent=self,
            statusTip="Save the current pipeline file to disk.",
            shortcut=QKeySequence("Ctrl+S"),
        )
        save_config_action.triggered.connect(self.save_pipeline)
        save_config_as_action = QAction(
            "Save Pipeline &As...",
            parent=self,
            statusTip="Save the current pipeline to a different pipeline file.",
            shortcut=QKeySequence("Ctrl+Shift+S"),
        )
        save_config_as_action.triggered.connect(self.save_pipeline_as)
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(new_config_action)
        file_menu.addAction(load_config_action)
        file_menu.addSeparator()
        file_menu.addAction(save_config_action)
        file_menu.addAction(save_config_as_action)
        # BIDS Menu
        sample_action = QAction(
            "&Add Sample BIDS Data", parent=self, statusTip="Add Sample BIDS Data"
        )
        sample_action.triggered.connect(self.add_sample_bids)
        bids_menu = self.menuBar().addMenu("&BIDS")
        bids_menu.addAction(sample_action)
        bids_menu.addSeparator()

        # Plugin Menu
        load_plugin_path_action = QAction(
            "&Load Plugin from Path",
            parent=self,
            statusTip="Load a plugin from a configuration file.",
        )
        load_plugin_path_action.triggered.connect(self.load_plugin_path)
        load_plugin_module_action = QAction(
            "&Load Plugin from Module",
            parent=self,
            statusTip="Load a plugin from a Python module.",
        )
        load_plugin_module_action.triggered.connect(self.load_plugin_module)
        load_plugin_github_action = QAction(
            "&Load Plugin from GitHub",
            parent=self,
            statusTip="Load a plugin from a GitHub repository.",
        )
        load_plugin_github_action.triggered.connect(self.load_plugin_github)
        manage_plugins_action = QAction(
            "&Manage Plugins",
            parent=self,
            statusTip="View, disable or remove loaded plugins.",
        )
        manage_plugins_action.triggered.connect(self.manage_plugins)
        plugin_menu = self.menuBar().addMenu("&Plugins")
        plugin_menu.addAction(load_plugin_path_action)
        plugin_menu.addAction(load_plugin_module_action)
        plugin_menu.addAction(load_plugin_github_action)
        plugin_menu.addSeparator()
        plugin_menu.addAction(manage_plugins_action)
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

        node_picker_action = QAction(
            "&Node Picker", parent=self, statusTip="Open the categorized node picker."
        )
        node_picker_action.triggered.connect(self.show_node_picker)
        view_menu = self.menuBar().addMenu("&View")
        view_menu.addAction(node_picker_action)

        # Pipeline Menu
        self.menuBar().addAction(exit_action)

        # Show the main window
        self.show()

        # Initialize on last opened screen
        screen_name = self.settings.get("screen_name")
        if screen_name is not None:
            for screen in QApplication.screens():
                if screen.name() == screen_name:
                    self.windowHandle().setScreen(screen)
                    break

    def finalize_controller_setup(self):
        """Load the current project config after the controller has finished setup."""
        self.viewer.load_nodes(self.controller.get("node_config"))
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
    def show_node_picker(self):
        """Show the categorized node picker dialog."""
        if self.node_picker is None:
            self.node_picker = NodePicker(self.controller, self)
            self.viewer.node_picker = self.node_picker
        self.node_picker.show()
        self.node_picker.raise_()
        self.node_picker.activateWindow()

    def new_pipeline(self):
        config_path = self.controller.new_config()
        if config_path is None:
            return
        if self.viewer is not None:
            self.viewer.load_nodes(self.controller.get("node_config"))
        self.statusBar().showMessage(f"{self.controller.name} is ready.")

    def load_pipeline(self):
        config_path = self.controller.load_config()
        if config_path is None:
            return
        if self.viewer is not None:
            self.viewer.load_nodes(self.controller.get("node_config"))
        self.statusBar().showMessage(f"{self.controller.name} is ready.")

    def save_pipeline(self):
        config_path = self.controller.save_config()
        if config_path is None:
            return
        self.statusBar().showMessage(f"{self.controller.name} saved to {config_path}.")

    def save_pipeline_as(self):
        config_path = self.controller.save_config_as()
        if config_path is None:
            return
        self.statusBar().showMessage(f"{self.controller.name} saved as {config_path}.")

    def load_plugin_path(self):
        plugin_path = get_user_input(
            "Select a plugin configuration file to load.",
            input_type="file",
            file_filter="JSON files (*.json)",
            parent=self,
        )
        if plugin_path is None:
            return
        self.controller.load_plugin_path(plugin_path)
        self.statusBar().showMessage(f"Plugin loaded from {plugin_path}.")

    def load_plugin_module(self):
        plugin_name = get_user_input(
            "Enter the name of the plugin module to load.",
            input_type="text",
            parent=self,
        )
        if plugin_name is None:
            return
        self.controller.load_plugin_module_name(plugin_name, ask_before_install=False)
        self.statusBar().showMessage(f"Plugin loaded from module '{plugin_name}'.")

    def load_plugin_github(self):
        plugin_url = get_user_input(
            "Enter the GitHub URL of the plugin to load.", input_type="url", parent=self
        )
        if plugin_url is None:
            return
        self.controller.load_plugin_github(plugin_url, ask_before_install=False)
        self.statusBar().showMessage(f"Plugin loaded from GitHub URL '{plugin_url}'.")

    def manage_plugins(self):
        from mne_nodes.gui.parameter.plugin_manager import PluginManagerDlg

        PluginManagerDlg(self, self.controller)

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
            command = [
                (sys.executable, "-m", "pip", "install", "--upgrade", "mne_nodes")
            ]
        else:
            command = [
                (
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "https://github.com/marsipu/mne-nodes/zipball/main",
                )
            ]
        if iswin and not _run_from_script():
            information_message(
                f"Manual install required! To update you need to exit the program and type '{command}' into the terminal!",
                parent=self,
            )

        else:
            # Register with controller for central tracking
            ProcessDialog(
                command,
                parent=self,
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
        command = [(sys.executable, "-m", "pip", "install", "--upgrade", "mne")]
        ProcessDialog(
            command,
            parent=self,
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
        _widgets["viewer"] = None
        self.controller.set("node_config", self.viewer.to_dict())
        self.controller.flush()
        event.accept()
