"""Metadata editor for newly saved plugin distributions."""

from importlib.metadata import EntryPoint
from shutil import which

from qtpy.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from mne_nodes.backend.exception_handling import get_exception_tuple
from mne_nodes.backend.package_utils import get_plugin_entry_points
from mne_nodes.backend.plugin_package import LICENSE_TEMPLATES, PluginPackageMetadata
from mne_nodes.gui.dialogs import ErrorDialog


class PluginPackageDialog(QDialog):
    """Collect and validate distribution metadata without executing plugin code."""

    def __init__(self, plugin_name: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.metadata: PluginPackageMetadata | None = None
        self.setWindowTitle("Plugin Package Metadata")
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Create an installable Python package. Review dependencies and "
                "licensing before publishing."
            )
        )
        form = QFormLayout()
        layout.addLayout(form)
        self.distribution_name = QLineEdit(f"mne-nodes_{plugin_name.replace('_', '-')}")
        self.version = QLineEdit("0.1.0")
        self.description = QLineEdit()
        self.author = QLineEdit()
        self.author_email = QLineEdit()
        self.repository_url = QLineEdit()
        self.dependencies = QPlainTextEdit()
        self.dependencies.setPlaceholderText(
            "One Python requirement per line, e.g. mne>=1.10\n"
            "mne-nodes is included automatically. System tools are not pip packages."
        )
        self.dependencies.setMaximumHeight(100)
        self.license_choice = QComboBox()
        self.license_choice.addItems(
            ["Choose a license...", *LICENSE_TEMPLATES, "Other SPDX license"]
        )
        self.license_expression = QLineEdit()
        self.license_text = QPlainTextEdit()
        self.license_text.setPlaceholderText(
            "Complete license text for a custom license"
        )
        self.license_text.setMaximumHeight(120)
        for label, field in (
            ("Distribution name", self.distribution_name),
            ("Version", self.version),
            ("Description", self.description),
            ("Author / copyright holder", self.author),
            ("Author email (optional)", self.author_email),
            ("Repository URL (optional)", self.repository_url),
            ("Additional dependencies", self.dependencies),
            ("License", self.license_choice),
            ("Custom SPDX expression", self.license_expression),
            ("Custom license text", self.license_text),
        ):
            form.addRow(label, field)
        self.license_choice.currentTextChanged.connect(self._license_changed)
        self._license_changed(self.license_choice.currentText())
        self.initialize_git = QCheckBox("Initialize a Git repository")
        git_available = which("git") is not None
        self.initialize_git.setChecked(git_available)
        self.initialize_git.setEnabled(git_available)
        self.initial_branch = QLineEdit("main")
        self.initial_branch.setEnabled(git_available)
        self.initialize_git.toggled.connect(self.initial_branch.setEnabled)
        form.addRow("Version control", self.initialize_git)
        form.addRow("Initial branch", self.initial_branch)
        layout.addWidget(
            QLabel(
                "No commits, remotes or uploads are created. Existing repositories "
                "are left unchanged."
                if git_available
                else "Git is unavailable; the package will be saved without a repository."
            )
        )
        self.install_package = QCheckBox("Install package after saving")
        self.editable_install = QCheckBox("Editable installation (link to source)")
        self.editable_install.setChecked(True)
        self.editable_install.setEnabled(False)
        self.install_package.toggled.connect(self.editable_install.setEnabled)
        form.addRow("Installation (optional)", self.install_package)
        form.addRow("", self.editable_install)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _license_changed(self, choice: str) -> None:
        custom = choice == "Other SPDX license"
        self.license_expression.setEnabled(custom)
        self.license_text.setEnabled(custom)

    def accept(self) -> None:
        """Keep the editor open when metadata is invalid."""
        choice = self.license_choice.currentText()
        metadata = PluginPackageMetadata(
            distribution_name=self.distribution_name.text().strip(),
            version=self.version.text().strip(),
            description=self.description.text().strip(),
            author=self.author.text().strip(),
            author_email=self.author_email.text().strip(),
            repository_url=self.repository_url.text().strip(),
            dependencies=tuple(
                line.strip()
                for line in self.dependencies.toPlainText().splitlines()
                if line.strip()
            ),
            license_expression=(
                choice
                if choice in LICENSE_TEMPLATES
                else (
                    self.license_expression.text().strip()
                    if choice == "Other SPDX license"
                    else ""
                )
            ),
            license_text=(
                self.license_text.toPlainText()
                if choice == "Other SPDX license"
                else ""
            ),
            initialize_git=self.initialize_git.isChecked(),
            initial_branch=self.initial_branch.text().strip(),
            install_package=self.install_package.isChecked(),
            editable_install=self.editable_install.isChecked(),
        )
        try:
            metadata.validate()
        except ValueError:
            ErrorDialog(
                get_exception_tuple(), self, "Invalid plugin package metadata."
            ).open()
            return
        self.metadata = metadata
        super().accept()


def request_package_metadata(
    plugin_name: str, parent: QWidget | None = None
) -> PluginPackageMetadata | None:
    """Return validated metadata, or None when creation is cancelled."""
    dialog = PluginPackageDialog(plugin_name, parent)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        return dialog.metadata
    return None


class InstalledPluginDialog(QDialog):
    """Choose one installed registration without importing any plugin."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Load Installed Plugin")
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Select a plugin to activate in this project. Only load code you trust."
            )
        )
        self.plugins = QComboBox()
        self._entries: list[EntryPoint] = []
        for entry in get_plugin_entry_points():
            distribution = entry.dist
            if distribution is None:
                continue
            self._entries.append(entry)
            self.plugins.addItem(
                f"{entry.name} - {distribution.name} {distribution.version} "
                f"({entry.value})"
            )
        layout.addWidget(self.plugins)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        load_button = buttons.addButton("Load", QDialogButtonBox.ButtonRole.AcceptRole)
        load_button.setEnabled(self.plugins.count() > 0)
        if self.plugins.count() == 0:
            layout.addWidget(
                QLabel("No installed plugins found. Install a plugin package first.")
            )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_registration(self) -> tuple[str, str]:
        """Return the distribution and entry-point name selected for activation."""
        index = self.plugins.currentIndex()
        if not 0 <= index < len(self._entries):
            raise ValueError("Select an installed plugin first.")
        entry = self._entries[index]
        if entry.dist is None:
            raise ValueError("The selected entry point has no distribution metadata.")
        return entry.dist.name, entry.name


class LocalPluginInstallDialog(QDialog):
    """Expose optional installation before loading a local package."""

    def __init__(self, project_root, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Load Local Plugin")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Project: {project_root}"))
        self.install_package = QCheckBox("Install package into the current environment")
        self.editable_install = QCheckBox("Editable installation (link to source)")
        self.editable_install.setChecked(True)
        self.editable_install.setEnabled(False)
        self.install_package.toggled.connect(self.editable_install.setEnabled)
        layout.addWidget(self.install_package)
        layout.addWidget(self.editable_install)
        layout.addWidget(
            QLabel(
                "Installation is optional. Editable installs keep changes linked to "
                "this source folder; ordinary installs copy files into the environment."
            )
        )
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
