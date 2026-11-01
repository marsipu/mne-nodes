"""Editable report preview before sharing an error with GitHub."""

from urllib.parse import urlencode

from qtpy.QtCore import QUrl
from qtpy.QtGui import QDesktopServices
from qtpy.QtWidgets import (
    QApplication,
    QDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from mne_nodes.gui.gui_utils import set_ratio_geometry

ISSUE_URL = "https://github.com/marsipu/mne-nodes/issues/new"


class IssueReportDialog(QDialog):
    """Let the user review and edit a report before opening an issue draft."""

    def __init__(self, report: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Review GitHub issue report")
        layout = QVBoxLayout(self)
        warning = QLabel(
            "Review and remove any private information before sharing. "
            "Automatic redaction cannot identify everything in error messages; "
            "relative filenames and other identifiers may remain. "
            "Opening GitHub creates a draft, not a submitted issue. "
            "The reviewed report is also copied to the clipboard; paste it into "
            "the issue if the report is too long to prefill."
        )
        warning.setWordWrap(True)
        layout.addWidget(warning)
        self.report_edit = QTextEdit()
        self.report_edit.setAcceptRichText(False)
        self.report_edit.setPlainText(report)
        layout.addWidget(self.report_edit)
        self.open_bt = QPushButton("Copy report and open GitHub")
        self.open_bt.clicked.connect(self.open_issue)
        layout.addWidget(self.open_bt)
        cancel_bt = QPushButton("Cancel")
        cancel_bt.clicked.connect(self.reject)
        layout.addWidget(cancel_bt)
        set_ratio_geometry(0.6, self)

    def open_issue(self) -> None:
        """Copy the reviewed report and open a browser, with a length fallback."""
        report = self.report_edit.toPlainText()
        QApplication.clipboard().setText(report)
        url = ISSUE_URL + "?" + urlencode({"title": "Error report", "body": report})
        if len(url) > 8000:
            url = ISSUE_URL
        if QDesktopServices.openUrl(QUrl(url)):
            self.accept()
        else:
            QMessageBox.warning(
                self,
                "Could not open browser",
                f"The report was copied. Open {ISSUE_URL} and paste it manually.",
            )
