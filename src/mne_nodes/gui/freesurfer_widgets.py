"""Dialogs for copying FreeSurfer subjects into the current dataset."""

from pathlib import Path

from qtpy.QtCore import Signal
from qtpy.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from mne_nodes.backend.exception_handling import ExceptionTuple, gui_error
from mne_nodes.backend.freesurfer import (
    find_freesurfer_subjects,
    import_freesurfer_subjects,
    is_freesurfer_subject,
)
from mne_nodes.gui.dialogs import ErrorDialog
from mne_nodes.gui.run_widgets import WorkerDialog
from mne_nodes.gui.user_interaction import get_user_input, warning_message
from mne_nodes.gui.widgets.list_widgets import CheckList


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
            "Copy existing reconstructions into this dataset's "
            "derivatives/freesurfer folder. Original folders and subject names are "
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
