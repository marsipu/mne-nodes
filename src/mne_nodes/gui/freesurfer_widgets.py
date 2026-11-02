"""Dialogs for copying FreeSurfer subjects into the current dataset."""

from pathlib import Path

from qtpy.QtCore import Signal
from qtpy.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)

from mne_nodes import iswin
from mne_nodes.backend.exception_handling import ExceptionTuple, gui_error
from mne_nodes.backend.execution import Worker
from mne_nodes.backend.freesurfer import (
    FreeSurferRuntime,
    find_freesurfer_subjects,
    import_freesurfer_subjects,
    is_freesurfer_subject,
)
from mne_nodes.gui.dialogs import ErrorDialog
from mne_nodes.gui.run_widgets import WorkerDialog
from mne_nodes.gui.user_interaction import get_user_input, warning_message
from mne_nodes.gui.widgets.list_widgets import CheckList


class FreeSurferSetupDialog(QDialog):
    """Discover FreeSurfer/WSL and explain installation without changing the OS."""

    def __init__(self, controller, parent=None) -> None:
        super().__init__(parent)
        self.ct = controller
        self.setWindowTitle("FreeSurfer setup")
        self.resize(760, 650)
        layout = QVBoxLayout(self)
        help_text = QTextBrowser()
        help_text.setOpenExternalLinks(True)
        help_text.setHtml(
            "<h3>FreeSurfer environment</h3>"
            "<p>FreeSurfer and Python are discovered automatically, inside "
            "WSL on Windows. Commands only need FreeSurfer; "
            "Python functions also need MNE. Discovery never installs software.</p>"
            + (
                "<p>1. Install WSL/Ubuntu using Microsoft's instructions "
                "(administrator access/restart may be needed): "
                '<a href="https://learn.microsoft.com/windows/wsl/install">'
                "Install WSL</a>.</p>"
                "<p>2. Inside Ubuntu, install FreeSurfer for Linux and its license. "
                "The Windows installation cannot be used.</p>"
                "<p>3. Inside Ubuntu, install Miniforge/Miniconda, then run:</p>"
                "<pre>conda create -n mne --override-channels -c conda-forge "
                "mne-base nibabel\n"
                'conda run -n mne python -c "import mne; print(mne.__version__)"'
                "</pre><p>A full graphical MNE installation is not required "
                "for watershed BEM.</p>"
                if iswin
                else "<p>Install FreeSurfer for your platform and register its license. "
                "Python functions use the current MNE-Nodes Python interpreter.</p>"
            )
            + '<p><a href="https://surfer.nmr.mgh.harvard.edu/fswiki/DownloadAndInstall">'
            "FreeSurfer installation/license</a> | "
            '<a href="https://mne.tools/stable/install/manual_install.html">'
            "MNE installation</a> | "
            '<a href="https://conda-forge.org/download/">Miniforge</a></p>'
            "<p>Discovery checks FREESURFER_HOME, recon-all on PATH and standard "
            "FreeSurfer locations. Your interactive login shell is loaded first, "
            "including .bashrc, Conda setup and FS_LICENSE. WSL Python discovery "
            "checks PATH, Conda's "
            "environment registry and standard Miniconda/Miniforge locations. "
            "To prioritize an installation, configure FREESURFER_HOME and "
            "activate the desired Python environment in your shell startup.</p>"
        )
        layout.addWidget(help_text)
        form = QFormLayout()
        self.distribution = QLineEdit(
            str(controller.settings.get("wsl_distribution") or "")
        )
        self.distribution.setEnabled(iswin)
        form.addRow("WSL distribution (empty = default)", self.distribution)
        layout.addLayout(form)
        self.status = QPlainTextEdit()
        self.status.setReadOnly(True)
        self.status.setPlainText("Click Discover to check the installation.")
        layout.addWidget(self.status)
        self.discover_button = QPushButton("Discover")
        self.discover_button.clicked.connect(self.discover)
        layout.addWidget(self.discover_button)
        plugin_hint = QLabel(
            "FreeSurfer nodes are provided by the mne-nodes_freesurfer plugin. "
            "Manage it using Plugins > Manage Plugins or "
            "Plugins > Load Plugin from Path."
        )
        plugin_hint.setWordWrap(True)
        layout.addWidget(plugin_hint)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        layout.addWidget(close)

    def discover(self) -> None:
        """Check installations in a worker so WSL startup cannot block Qt."""
        if self.distribution.isEnabled():
            self.ct.settings.set(
                "wsl_distribution", self.distribution.text().strip() or None
            )
        self.discover_button.setEnabled(False)
        self.status.setPlainText("Checking FreeSurfer and Python...")
        self.worker = Worker(self.ct.freesurfer_runtime)
        self.worker.signals.finished.connect(self._discovered)
        self.worker.signals.error.connect(self._discovery_error)
        self.worker.start()

    def _discovered(self, runtime: FreeSurferRuntime) -> None:
        self.discover_button.setEnabled(True)
        self.status.setPlainText(
            f"FreeSurfer: {runtime.fs_path}\n"
            f"Python with MNE: {runtime.python or 'NOT FOUND - see instructions above'}\n"
            f"WSL distribution: {runtime.distribution or 'default'}\n"
            "A valid FreeSurfer license is also required for processing."
        )

    def _discovery_error(self, error: ExceptionTuple) -> None:
        self.discover_button.setEnabled(True)
        self.status.setPlainText(f"Discovery failed:\n{error}")


class FreeSurferImportDialog(QDialog):
    """Select and copy one or multiple existing FreeSurfer reconstructions."""

    subjects_imported = Signal()

    def __init__(self, controller, parent=None) -> None:
        super().__init__(parent)
        self.ct = controller
        self.sources: dict[str, Path] = {}
        self.checked: list[str] = []
        self.setWindowTitle("Import FreeSurfer subjects")
        self.resize(650, 450)
        layout = QVBoxLayout(self)
        description = QLabel(
            "Copy existing reconstructions into this dataset's FreeSurfer subjects "
            "directory (derivatives/freesurfer/subjects when present, otherwise "
            "derivatives/freesurfer). Original folders and subject names are "
            "preserved. Existing destination subjects are never overwritten."
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        choices = QHBoxLayout()
        self.single_button = QPushButton("Choose subject folder...")
        self.single_button.clicked.connect(self._choose_subject)
        choices.addWidget(self.single_button)
        self.directory_button = QPushButton("Choose subjects directory...")
        self.directory_button.clicked.connect(self._choose_directory)
        choices.addWidget(self.directory_button)
        layout.addLayout(choices)
        self.subjects = CheckList([], checked=self.checked, ui_button_pos="bottom")
        self.subjects.checkedChanged.connect(self._selection_changed)
        layout.addWidget(self.subjects)
        self.status = QLabel("Choose an existing subject or a directory of subjects.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.import_button = QPushButton("Import selected subjects")
        self.import_button.clicked.connect(self._import)
        self.import_button.setEnabled(False)
        layout.addWidget(self.import_button)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        layout.addWidget(close)

    def _choose_subject(self) -> None:
        self._choose_source(single=True)

    def _choose_directory(self) -> None:
        self._choose_source(single=False)

    def _choose_source(self, *, single: bool) -> None:
        selected = get_user_input(
            "Select a FreeSurfer subject folder"
            if single
            else "Select a FreeSurfer subjects directory",
            "folder",
            cancel_allowed=True,
        )
        if selected is None:
            return
        with gui_error():
            source = Path(selected)
            if single:
                if not is_freesurfer_subject(source):
                    raise ValueError(
                        f"Expected mri, surf and label directories in {source}."
                    )
                sources = [source]
            else:
                sources = find_freesurfer_subjects(source)
            if not sources:
                warning_message(
                    "No subjects with mri, surf and label directories found.",
                    parent=self,
                )
                return
            self.sources = {path.name: path for path in sources}
            self.checked.clear()
            self.checked.extend(self.sources)
            self.subjects.replace_data(list(self.sources))
            self.subjects.content_changed()
            self._selection_changed()
            self.status.setText(f"Source: {source}")

    def _selection_changed(self, _selected=None) -> None:
        self.import_button.setEnabled(bool(self.checked))

    def _import(self) -> None:
        if not self.checked:
            warning_message("Select at least one subject to import.", parent=self)
            return
        with gui_error():
            destination = self.ct.ensure_subjects_dir()
            worker = WorkerDialog(
                self,
                import_freesurfer_subjects,
                sources=[self.sources[name] for name in self.checked],
                destination=destination,
                show_buttons=True,
                blocking=True,
                return_exception=True,
                title="Importing FreeSurfer subjects",
            )
            result = worker.return_value
            if isinstance(result, ExceptionTuple):
                self.status.setText(
                    f"Import failed. Completed subjects, if any, remain in {destination}."
                )
                ErrorDialog(result, parent=self).exec()
                self.subjects_imported.emit()
                return
            canceled = "Import canceled. " if len(result) < len(self.checked) else ""
            self.status.setText(
                f"{canceled}Imported {len(result)} of {len(self.checked)} subject(s) into "
                f"{destination}. Originals were not modified."
            )
            if result:
                completed = {path.name for path in result}
                self.checked[:] = [
                    name for name in self.checked if name not in completed
                ]
                self.subjects.content_changed()
                self._selection_changed()
                self.subjects_imported.emit()
