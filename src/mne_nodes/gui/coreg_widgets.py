"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory

import mne
from qtpy.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from mne_nodes.backend.coregistration import (
    CoregGroup,
    automatic_coregistration,
    discover_coreg_groups,
    save_group_trans,
    trans_path,
)
from mne_nodes.backend.exception_handling import ExceptionTuple, gui_error
from mne_nodes.gui.dialogs import ErrorDialog
from mne_nodes.gui.freesurfer_widgets import FreeSurferImportDialog
from mne_nodes.gui.run_widgets import WorkerDialog
from mne_nodes.gui.user_interaction import ask_user, warning_message
from mne_nodes.gui.widgets.list_widgets import MarkList


class CoregDialog(QDialog):
    """Manage transformations for raw recordings with verified shared digitization."""

    def __init__(self, controller, parent=None) -> None:
        super().__init__(parent)
        self.ct = controller
        self.groups: dict[str, CoregGroup] = {}
        self._worker = None
        self._manual = None
        self._manual_files = None
        self.setWindowTitle("Head-to-MRI Coregistration")
        self.resize(850, 650)

        layout = QVBoxLayout(self)
        description = QLabel(
            "Recordings are grouped only within a subject/session and with identical "
            "digitization.\nA check mark means a transformation exists, not that its "
            "alignment is correct."
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        lists = QHBoxLayout()
        self.group_list = MarkList(title="Digitization groups")
        self.group_list.currentChanged.connect(self._group_changed)
        lists.addWidget(self.group_list, 1)
        self.recording_list = MarkList(title="Recordings / transformation availability")
        self.recording_list.currentChanged.connect(self._recording_changed)
        lists.addWidget(self.recording_list, 1)
        layout.addLayout(lists, 1)
        subject_layout = QHBoxLayout()
        subject_layout.addWidget(QLabel("FreeSurfer subject:"))
        self.mri_subject = QComboBox()
        self.mri_subject.currentTextChanged.connect(self._subject_changed)
        subject_layout.addWidget(self.mri_subject)
        self.import_button = QPushButton("Import FreeSurfer subjects...")
        self.import_button.clicked.connect(self._import_subjects)
        subject_layout.addWidget(self.import_button)
        layout.addLayout(subject_layout)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        buttons = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.update_widgets)
        self.auto_button = QPushButton("Automatic coregistration")
        self.auto_button.clicked.connect(self._automatic)
        self.manual_button = QPushButton("Manual coregistration / inspect")
        self.manual_button.clicked.connect(self._open_manual)
        self.reuse_button = QPushButton("Reuse selected transformation for group")
        self.reuse_button.clicked.connect(self._reuse)
        for button in (
            self.refresh_button,
            self.auto_button,
            self.manual_button,
            self.reuse_button,
        ):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self._update_buttons()

    def _import_subjects(self) -> None:
        dialog = FreeSurferImportDialog(self.ct, self)
        dialog.subjects_imported.connect(self._subjects_imported)
        dialog.open()

    def _subjects_imported(self) -> None:
        selected = self.mri_subject.currentText()
        self.mri_subject.blockSignals(True)
        self.mri_subject.clear()
        self.mri_subject.addItem("")
        self.mri_subject.addItems(sorted(self.ct.get_datatype_items("subject")))
        self.mri_subject.setCurrentText(selected)
        self.mri_subject.blockSignals(False)
        self._group_changed(self.group_list.get_current())
        viewer = self.ct.viewer
        if viewer is not None and viewer.input_node is not None:
            viewer.input_node.update_widgets()

    def update_widgets(self) -> None:
        """Discover recordings in a worker, without loading raw signal samples."""
        with gui_error():
            self.ct.ensure_bids_root()
            self.ct.ensure_deriv_root()
            subjects_dir = self.ct.ensure_subjects_dir()
            self.mri_subject.blockSignals(True)
            self.mri_subject.clear()
            self.mri_subject.addItem("")
            self.mri_subject.addItems(sorted(self.ct.get_datatype_items("subject")))
            self.mri_subject.blockSignals(False)
            self.status.setText(f"FreeSurfer subjects: {subjects_dir}")
            self._start_worker(
                discover_coreg_groups, self._discovered, controller=self.ct
            )

    def _start_worker(self, function, callback, **kwargs) -> None:
        self._worker = WorkerDialog(
            self,
            function,
            show_buttons=True,
            return_exception=True,
            title="Coregistration",
            **kwargs,
        )
        self._worker.thread_finished.connect(partial(self._worker_finished, callback))
        self._update_buttons()

    def _worker_finished(self, callback, result) -> None:
        self._worker = None
        if isinstance(result, ExceptionTuple):
            ErrorDialog(result, parent=self).exec()
        else:
            callback(result)
        self._update_buttons()

    def _discovered(self, groups: list[CoregGroup]) -> None:
        self.groups = {}
        for group in groups:
            path = group.recordings[0].bids_path
            session = f"ses-{path.session}" if path.session else "no session"
            label = (
                f"sub-{path.subject} / {session} / digitization {len(self.groups) + 1}"
                f" ({len(group.recordings)} recordings)"
            )
            self.groups[label] = group
        self._refresh_marks()
        if self.groups:
            self.group_list.view.setCurrentIndex(self.group_list.model.index(0, 0))
            self._group_changed(self.group_list.get_current())
        else:
            self.recording_list.replace_data({})
            self.status.setText("No raw recordings found.")

    def _current_group(self) -> CoregGroup | None:
        current = self.group_list.get_current()
        return self.groups.get(current) if current is not None else None

    def _refresh_marks(self) -> None:
        self.group_list.replace_data(
            {
                label: all(
                    r.existing_trans is not None and r.existing_trans.is_file()
                    for r in group.recordings
                )
                for label, group in self.groups.items()
            }
        )
        group = self._current_group()
        if group:
            self.recording_list.replace_data(
                {
                    r.bids_path.basename: (
                        r.existing_trans is not None and r.existing_trans.is_file()
                    )
                    for r in group.recordings
                }
            )

    def _group_changed(self, current, previous=None) -> None:
        group = self.groups.get(current)
        if group is None:
            return
        self._refresh_marks()
        recording = group.recordings[0]
        saved = self.ct.get("coreg_subjects", {}).get(recording.bids_path.basename)
        subject = recording.bids_path.subject
        candidates = (saved, f"sub-{subject}", subject)
        selected = next(
            (s for s in candidates if s and self.mri_subject.findText(s) >= 0), ""
        )
        self.mri_subject.setCurrentText(selected)
        self._subject_changed(selected)
        self.status.setText(
            recording.error
            or "Choose a FreeSurfer subject, then fit or inspect alignment."
        )
        self.recording_list.view.setCurrentIndex(self.recording_list.model.index(0, 0))
        self._update_buttons()

    def _recording_changed(self, current, previous=None) -> None:
        group = self._current_group()
        if group:
            recording = next(
                (r for r in group.recordings if r.bids_path.basename == current), None
            )
            if recording:
                self.status.setText(
                    recording.error
                    or (
                        str(recording.existing_trans)
                        if recording.existing_trans
                        else "No transformation found."
                    )
                )
        self._update_buttons()

    def _subject_changed(self, subject: str) -> None:
        group = self._current_group()
        if group and subject:
            mapping = self.ct.get("coreg_subjects", {}).copy()
            mapping.update({r.bids_path.basename: subject for r in group.recordings})
            self.ct.set("coreg_subjects", mapping)
        self._update_buttons()

    def _update_buttons(self) -> None:
        available = self._worker is None and self._manual is None
        group = self._current_group()
        usable = available and group is not None and not group.recordings[0].error
        self.refresh_button.setEnabled(available)
        self.import_button.setEnabled(available)
        self.group_list.setEnabled(available)
        self.recording_list.setEnabled(available)
        self.mri_subject.setEnabled(available)
        self.auto_button.setEnabled(bool(usable and self.mri_subject.currentText()))
        self.manual_button.setEnabled(bool(usable and self.mri_subject.currentText()))
        self.reuse_button.setEnabled(bool(usable and self._selected_trans()))

    def _selected_trans(self) -> Path | None:
        group = self._current_group()
        if group:
            name = self.recording_list.get_current()
            return next(
                (
                    r.existing_trans
                    for r in group.recordings
                    if r.bids_path.basename == name
                ),
                None,
            )
        return None

    def _confirm_overwrite(self, group: CoregGroup) -> bool:
        root = self.ct.ensure_deriv_root(interactive=False)
        existing = any(trans_path(r.bids_path, root).exists() for r in group.recordings)
        return not existing or bool(
            ask_user(
                "Replace existing recording-specific transformations in this group?",
                parent=self,
            )
        )

    def _automatic(self) -> None:
        group = self._current_group()
        if group is None or not self._confirm_overwrite(group):
            return
        self._start_worker(
            automatic_coregistration,
            self._fit_finished,
            group=group,
            subject=self.mri_subject.currentText(),
            subjects_dir=self.ct.ensure_subjects_dir(interactive=False),
            deriv_root=self.ct.ensure_deriv_root(interactive=False),
            overwrite=True,
        )

    def _fit_finished(self, message: str) -> None:
        self._refresh_marks()
        self.status.setText(message)

    def _reuse(self) -> None:
        group, source = self._current_group(), self._selected_trans()
        if group is None or source is None or not self._confirm_overwrite(group):
            return
        with gui_error():
            trans = mne.read_trans(source, return_all=False)
            if not isinstance(trans, mne.transforms.Transform):
                raise TypeError(f"Invalid transformation in {source}.")
            paths = save_group_trans(
                group,
                trans,
                self.ct.ensure_deriv_root(interactive=False),
                overwrite=True,
            )
            self._fit_finished(f"Saved {len(paths)} transformations from {source}.")

    def _open_manual(self) -> None:
        group = self._current_group()
        if group is None:
            return
        with gui_error():
            files = TemporaryDirectory(prefix="mne-nodes-coreg-")
            self._manual_files = files
            try:
                # An info FIF preserves BIDS electrode sidecars for non-FIF inputs.
                info_path = Path(files.name) / "recording-info.fif"
                mne.io.write_info(info_path, group.info)
                mne.viz.set_3d_backend("pyvistaqt")
                ui = mne.gui.coregistration(
                    inst=str(info_path),
                    subject=self.mri_subject.currentText(),
                    subjects_dir=self.ct.ensure_subjects_dir(interactive=False),
                    trans=self._selected_trans(),
                    show=False,
                    block=False,
                )
                self._manual = ui
                self._route_manual_save(ui, group)
                ui._renderer._window.signal_close.connect(self._manual_closed)
                ui._renderer.show()
            except Exception:
                if self._manual is not None:
                    self._manual.close()
                    self._manual = None
                files.cleanup()
                self._manual_files = None
                raise
            self._update_buttons()

    def _route_manual_save(self, ui, group: CoregGroup) -> None:
        """Replace only this Qt instance's file-picker callback, not MNE globals."""
        button = ui._widgets["save_trans"]._widget
        if not isinstance(button, QPushButton):
            raise TypeError("This MNE version does not expose a Qt save button.")
        button.clicked.disconnect()
        button.clicked.connect(partial(self._save_manual, ui, group))
        button.setText("Save to derivatives")

        def lock_sources(_change=None):
            for name in (
                "subjects_dir",
                "subjects_dir_field",
                "subject",
                "info_file",
                "info_file_field",
                "scaling_mode",
            ):
                ui._widgets[name].set_enabled(False)

        # MNE re-enables input and scaling controls when locking MRI fiducials.
        ui.observe(lock_sources, names="_lock_fids")
        lock_sources()

    def _save_manual(self, ui, group: CoregGroup) -> None:
        with gui_error():
            if not self._confirm_overwrite(group):
                return
            paths = save_group_trans(
                group,
                ui.coreg.trans,
                self.ct.ensure_deriv_root(interactive=False),
                overwrite=True,
            )
            ui._trans_modified = False
            ui._display_message(f"Saved {len(paths)} transformations to derivatives.")
            self._fit_finished(f"Saved {len(paths)} transformations to derivatives.")

    def _manual_closed(self) -> None:
        self._manual = None
        if self._manual_files is not None:
            self._manual_files.cleanup()
            self._manual_files = None
        self._update_buttons()

    def closeEvent(self, event) -> None:
        """Keep worker and manual-GUI resources alive until their operations finish."""
        if self._worker is not None or self._manual is not None:
            warning_message("Close the coregistration operation first.", parent=self)
            event.ignore()
        else:
            event.accept()
