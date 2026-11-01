"""Error display, traceback copying and opt-in issue reporting."""

from qtpy.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from mne_nodes.backend.issue_reporting import anonymize_report, collect_diagnostics
from mne_nodes.gui.dialogs.issue_report_dialog import IssueReportDialog
from mne_nodes.gui.gui_utils import set_ratio_geometry
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

        set_ratio_geometry(0.6, self)
        self.init_ui()

    def init_ui(self) -> None:
        """Create the error display and reporting controls."""
        layout = QVBoxLayout()
        self.display = QTextEdit()
        self.display.setLineWrapMode(QTextEdit.WidgetWidth)
        self.display.setReadOnly(True)
        self.display.setPlainText(self.traceback_text)
        layout.addWidget(self.display)

        self.copy_bt = QPushButton("Copy traceback")
        self.copy_bt.clicked.connect(self.copy_traceback)
        layout.addWidget(self.copy_bt)

        self.include_diagnostics = QCheckBox(
            "Include anonymized system info, loaded plugins and dataset summary"
        )
        layout.addWidget(self.include_diagnostics)
        self.issue_bt = QPushButton("Open GitHub issue…")
        self.issue_bt.clicked.connect(self.open_issue)
        layout.addWidget(self.issue_bt)

        self.close_bt = QPushButton("Close")
        self.close_bt.clicked.connect(self.close)
        layout.addWidget(self.close_bt)
        self.setLayout(layout)

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
            main_window = get_widget("main_window")
            controller = getattr(main_window, "controller", None)
            report += "\n\n### Diagnostics\n\n" + collect_diagnostics(controller)
        IssueReportDialog(report, self).exec()


def show_error_dialog(exc_str):
    """Show an error if a QApplication is available; otherwise log a notice."""
    if QApplication.instance() is not None:
        ErrorDialog(exc_str, title="An unexpected error occurred").exec()
    else:
        logger.debug("No QApplication instance available.")
