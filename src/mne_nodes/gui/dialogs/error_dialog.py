"""Error display, traceback copying and opt-in issue reporting."""

from functools import partial

from qtpy.QtCore import Qt, QTimer
from qtpy.QtGui import QFontDatabase
from qtpy.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QStyle,
    QTextEdit,
    QVBoxLayout,
)

from mne_nodes.backend.issue_reporting import anonymize_report, collect_diagnostics
from mne_nodes.gui.dialogs.issue_report_dialog import IssueReportDialog
from mne_nodes.gui.widget_registry import get_widget
from mne_nodes.logger import logger


class ErrorDialog(QDialog):
    """Show an error locally and offer a user-reviewed GitHub report."""

    def __init__(self, exception_tuple, parent=None, title=None):
        super().__init__(parent)
        self.err = exception_tuple
        self.title = title
        self.setWindowTitle(title or "An Error occurred!")

        error_type = self.err[0]
        error_name = getattr(error_type, "__name__", str(error_type))
        error_line = f"{error_name}: {self.err[1]}"
        self.traceback_text = str(self.err[2])
        if not self.traceback_text.rstrip().endswith(error_line):
            self.traceback_text = f"{self.traceback_text.rstrip()}\n{error_line}\n"

        self.error_name = error_name
        self.init_ui()

    def init_ui(self) -> None:
        """Create the error display and reporting controls."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(12)
        icon = QLabel()
        error_icon = self.style().standardIcon(
            QStyle.StandardPixmap.SP_MessageBoxCritical
        )
        icon.setPixmap(error_icon.pixmap(32, 32))
        header.addWidget(icon, alignment=Qt.AlignmentFlag.AlignTop)
        summary = QVBoxLayout()
        heading = QLabel(self.error_name)
        heading.setTextFormat(Qt.TextFormat.PlainText)
        font = heading.font()
        font.setPointSize(font.pointSize() + 3)
        font.setBold(True)
        heading.setFont(font)
        summary.addWidget(heading)
        self.error_summary = QLabel(str(self.err[1]))
        self.error_summary.setTextFormat(Qt.TextFormat.PlainText)
        self.error_summary.setWordWrap(True)
        self.error_summary.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        summary.addWidget(self.error_summary)
        header.addLayout(summary, stretch=1)
        layout.addLayout(header)

        layout.addWidget(QLabel("Traceback"))
        self.display = QTextEdit()
        self.display.setAccessibleName("Error traceback")
        self.display.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.display.setFont(
            QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        )
        self.display.setReadOnly(True)
        self.display.setPlainText(self.traceback_text)
        layout.addWidget(self.display, stretch=1)

        report_group = QGroupBox("Report this error")
        report_layout = QVBoxLayout(report_group)
        report_help = QLabel(
            "Review and edit a redacted report before opening a GitHub issue draft. "
            "Nothing is submitted automatically."
        )
        report_help.setWordWrap(True)
        report_layout.addWidget(report_help)
        self.include_diagnostics = QCheckBox(
            "Include anonymized system info, loaded plugins and dataset summary"
        )
        report_layout.addWidget(self.include_diagnostics)
        layout.addWidget(report_group)

        actions = QHBoxLayout()
        self.copy_bt = QPushButton("Copy traceback")
        self.copy_bt.clicked.connect(self.copy_traceback)
        actions.addWidget(self.copy_bt)
        actions.addStretch()
        self.issue_bt = QPushButton("Open GitHub issue…")
        self.issue_bt.clicked.connect(self.open_issue)
        actions.addWidget(self.issue_bt)
        self.close_bt = QPushButton("Close")
        self.close_bt.clicked.connect(self.close)
        self.close_bt.setDefault(True)
        actions.addWidget(self.close_bt)
        layout.addLayout(actions)

    def copy_traceback(self) -> None:
        """Copy the original plain-text traceback, without redaction."""
        QApplication.clipboard().setText(self.traceback_text)

    def open_issue(self) -> None:
        """Preview a redacted report before opening GitHub."""
        text = self.traceback_text
        if self.title:
            text = f"{self.title}\n\n{text}"
        report = "### Error\n\n" + anonymize_report(text)
        if self.include_diagnostics.isChecked():
            # Execution imports the error dialogs, so defer this import.
            from mne_nodes.gui.dialogs.run_dialogs import WorkerDialog

            main_window = get_widget("main_window")
            controller = getattr(main_window, "controller", None)
            self.issue_bt.setEnabled(False)
            self._diagnostics_worker = WorkerDialog(
                self,
                partial(collect_diagnostics, controller),
                return_exception=True,
                title="Collecting diagnostics…",
            )
            self._diagnostics_worker.setWindowTitle("Collecting diagnostics")
            self._diagnostics_worker.progress_bar.setRange(0, 0)
            self._diagnostics_worker.progress_bar.show()
            self._diagnostics_worker.thread_finished.connect(
                partial(self._schedule_diagnostics_collected, report)
            )
            return
        IssueReportDialog(report, self).exec()

    def _schedule_diagnostics_collected(self, report: str, diagnostics: object) -> None:
        QTimer.singleShot(0, partial(self._diagnostics_collected, report, diagnostics))

    def _diagnostics_collected(self, report: str, diagnostics: object) -> None:
        from mne_nodes.backend.exception_handling import ExceptionTuple

        self.issue_bt.setEnabled(True)
        if isinstance(diagnostics, ExceptionTuple):
            QMessageBox.warning(
                self,
                "Could not collect diagnostics",
                f"{diagnostics[0].__name__}: {diagnostics[1]}\n\n"
                "Try again or uncheck diagnostics to report the original error.",
            )
            return
        if not isinstance(diagnostics, str):
            raise TypeError("Diagnostics collection must return report text.")
        IssueReportDialog(report + "\n\n### Diagnostics\n\n" + diagnostics, self).exec()


def show_error_dialog(exc_str):
    """Show an error if a QApplication is available; otherwise log a notice."""
    if QApplication.instance() is not None:
        ErrorDialog(exc_str, title="An unexpected error occurred").exec()
    else:
        logger.debug("No QApplication instance available.")
