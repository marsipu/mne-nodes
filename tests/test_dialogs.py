"""Test error reporting without contacting GitHub or sharing private data."""

from threading import Event, get_ident
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
from qtpy.QtCore import QObject, Qt, QTimer, Signal
from qtpy.QtGui import QFontDatabase
from qtpy.QtWidgets import QApplication, QTextEdit, QWidget

from mne_nodes.backend import issue_reporting
from mne_nodes.gui import dialogs
from mne_nodes.gui.dialogs import (
    ErrorDialog,
    ProgressDialog,
    SysInfoMsg,
    error_dialog,
    issue_report_dialog,
)
from mne_nodes.gui.dialogs.issue_report_dialog import ISSUE_URL, IssueReportDialog


@pytest.mark.parametrize(
    "traceback",
    [
        '  File "/private/data.py", line 1, in <module>\n    fail()\n',
        '  File "/private/data.py", line 1\nValueError: <private & literal>\n',
    ],
)
def test_copy_traceback(qtbot, traceback):
    dialog = ErrorDialog(
        (ValueError, ValueError("<private & literal>"), traceback),
        title="Loading <data>",
    )
    qtbot.addWidget(dialog)
    assert dialog.windowTitle() == "Loading <data>"
    assert "<private & literal>" in dialog.display.toPlainText()
    assert dialog.traceback_text.count("ValueError: <private & literal>") == 1
    qtbot.mouseClick(dialog.copy_bt, Qt.LeftButton)
    assert QApplication.clipboard().text() == dialog.traceback_text
    assert "/private/data.py" in QApplication.clipboard().text()


def test_issue_diagnostics_are_opt_in(qtbot, monkeypatch):
    reports = []
    monkeypatch.setattr(
        error_dialog.IssueReportDialog,
        "exec",
        lambda self: reports.append(self.report_edit.toPlainText()),
    )
    monkeypatch.setattr(
        error_dialog, "collect_diagnostics", lambda ct: pytest.fail("Not opted in")
    )
    dialog = ErrorDialog(
        ("ValueError", "Failed", '  File "C:\\private folder\\data.py"\n'),
        title="Failed to load /private/dataset.csv",
    )
    qtbot.addWidget(dialog)
    assert not dialog.include_diagnostics.isChecked()
    qtbot.mouseClick(dialog.issue_bt, Qt.LeftButton)
    assert len(reports) == 1
    assert "ValueError: Failed" in reports[0]
    assert "Diagnostics" not in reports[0]
    assert "private" not in reports[0]

    controller = object()
    monkeypatch.setattr(
        error_dialog, "get_widget", lambda name: SimpleNamespace(controller=controller)
    )
    monkeypatch.setattr(
        error_dialog,
        "collect_diagnostics",
        lambda ct: (
            "opt-in summary" if ct is controller else pytest.fail("Wrong context")
        ),
    )
    dialog.include_diagnostics.setChecked(True)
    qtbot.mouseClick(dialog.issue_bt, Qt.LeftButton)
    qtbot.waitUntil(lambda: len(reports) == 2)
    assert "### Diagnostics\n\nopt-in summary" in reports[1]


def test_report_preview_and_browser(qtbot, monkeypatch):
    urls = []
    monkeypatch.setattr(
        issue_report_dialog.QDesktopServices,
        "openUrl",
        lambda url: urls.append(url.toString()) or True,
    )
    dialog = IssueReportDialog("Original report")
    qtbot.addWidget(dialog)
    dialog.report_edit.setPlainText("Reviewed <traceback> & details\nsecond line")
    qtbot.mouseClick(dialog.open_bt, Qt.LeftButton)
    parsed = urlparse(urls[0])
    assert parsed.scheme == "https"
    assert parsed.netloc == "github.com"
    assert parsed.path == "/marsipu/mne-nodes/issues/new"
    assert parse_qs(parsed.query)["body"] == [QApplication.clipboard().text()]
    assert QApplication.clipboard().text() == dialog.report_edit.toPlainText()


def test_error_dialog_layout(qtbot):
    dialog = ErrorDialog((ValueError, "<literal error>", "Traceback"))
    qtbot.addWidget(dialog)
    dialog.show()
    assert dialog.error_summary.text() == "<literal error>"
    assert dialog.error_summary.textFormat() == Qt.TextFormat.PlainText
    assert dialog.display.isReadOnly()
    assert dialog.display.lineWrapMode() == QTextEdit.LineWrapMode.NoWrap
    fixed_font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    assert dialog.display.font().family() == fixed_font.family()
    assert dialog.close_bt.isDefault()
    assert dialog.copy_bt.y() == dialog.issue_bt.y() == dialog.close_bt.y()
    assert dialog.copy_bt.width() < dialog.width() / 2


@pytest.mark.parametrize("dismiss_worker", [False, True])
def test_diagnostics_worker_keeps_ui_responsive(qtbot, monkeypatch, dismiss_worker):
    from mne_nodes.gui.dialogs import run_dialogs
    from mne_nodes.gui.dialogs.run_dialogs import WorkerDialog

    started = Event()
    release = Event()
    threads = []
    reports = []
    worker_titles = []
    warnings = []
    main_thread = get_ident()

    def collect(controller):
        threads.append(get_ident())
        started.set()
        if not release.wait(timeout=5):
            raise TimeoutError("GUI did not respond during diagnostics collection")
        return "Worker diagnostics"

    dialog = ErrorDialog((ValueError, "Demo error", "Traceback"))
    qtbot.addWidget(dialog)
    dialog.include_diagnostics.setChecked(True)
    monkeypatch.setattr(error_dialog, "collect_diagnostics", collect)
    monkeypatch.setattr(
        run_dialogs, "warning_message", lambda *args, **kwargs: warnings.append(args)
    )
    monkeypatch.setattr(
        IssueReportDialog,
        "exec",
        lambda self: reports.append(self.report_edit.toPlainText()),
    )

    def check_progress():
        if not started.is_set():
            return
        workers = dialog.findChildren(WorkerDialog)
        if not workers:
            return
        worker = workers[0]
        worker_titles.append(worker.windowTitle())
        assert worker.isVisible()
        assert worker.progress_bar.isVisible()
        assert worker.progress_bar.maximum() == 0
        assert get_ident() == main_thread
        if dismiss_worker:
            worker.reject()
            assert worker.isVisible()
            assert warnings
            assert not reports
            assert not dialog.issue_bt.isEnabled()
        release.set()
        timer.stop()

    timer = QTimer(dialog)
    timer.setInterval(10)
    timer.timeout.connect(check_progress)
    timer.start()
    dialog.open_issue()
    assert not dialog.issue_bt.isEnabled()
    qtbot.waitUntil(lambda: len(reports) == 1, timeout=6000)
    timer.stop()
    assert threads and threads[0] != main_thread
    assert worker_titles == ["Collecting diagnostics"]
    assert len(reports) == 1
    assert reports[0].endswith("### Diagnostics\n\nWorker diagnostics")
    assert dialog.issue_bt.isEnabled()


def test_diagnostics_worker_failure_is_shown(qtbot, monkeypatch):
    def fail(controller):
        raise RuntimeError("Demo collection failure")

    warnings = []
    dialog = ErrorDialog((ValueError, "Original error", "Traceback"))
    qtbot.addWidget(dialog)
    dialog.include_diagnostics.setChecked(True)
    monkeypatch.setattr(error_dialog, "collect_diagnostics", fail)
    monkeypatch.setattr(
        error_dialog.QMessageBox, "warning", lambda *args: warnings.append(args)
    )
    monkeypatch.setattr(
        IssueReportDialog, "exec", lambda self: pytest.fail("No incomplete report")
    )
    dialog.open_issue()
    qtbot.waitUntil(lambda: len(warnings) == 1)
    assert len(warnings) == 1
    assert warnings[0][1] == "Could not collect diagnostics"
    assert "Demo collection failure" in warnings[0][2]
    assert "Original error" in dialog.display.toPlainText()
    assert dialog.issue_bt.isEnabled()


def test_long_report_clipboard_fallback(qtbot, monkeypatch):
    urls = []
    monkeypatch.setattr(
        issue_report_dialog.QDesktopServices,
        "openUrl",
        lambda url: urls.append(url.toString()) or True,
    )
    report = "Traceback\n" + "é" * 10000
    dialog = IssueReportDialog(report)
    qtbot.addWidget(dialog)
    dialog.open_issue()
    assert urls == [ISSUE_URL]
    assert QApplication.clipboard().text() == report


def test_cancel_report_does_not_share(qtbot, monkeypatch):
    monkeypatch.setattr(
        issue_report_dialog.QDesktopServices,
        "openUrl",
        lambda url: pytest.fail("Cancelled report must not open browser"),
    )
    QApplication.clipboard().setText("Previous clipboard")
    dialog = IssueReportDialog("Unshared report")
    qtbot.addWidget(dialog)
    dialog.reject()
    assert QApplication.clipboard().text() == "Previous clipboard"


def test_browser_failure_retains_report(qtbot, monkeypatch):
    warnings = []
    monkeypatch.setattr(
        issue_report_dialog.QDesktopServices, "openUrl", lambda url: False
    )
    monkeypatch.setattr(
        issue_report_dialog.QMessageBox,
        "warning",
        lambda *args: warnings.append(args[2]),
    )
    dialog = IssueReportDialog("Reviewed report")
    qtbot.addWidget(dialog)
    dialog.open_issue()
    assert QApplication.clipboard().text() == "Reviewed report"
    assert ISSUE_URL in warnings[0]
    assert dialog.result() != dialog.DialogCode.Accepted


@pytest.mark.parametrize(
    "private",
    [
        "/home/other person/dataset/raw.fif",
        r"C:\Users\Someone Else\dataset\raw.fif",
        r"\\private-server\share\raw.fif",
        "~/dataset/raw.fif",
        "someone@example.org",
        "192.168.12.3",
        "https://private-server.example.org/dataset",
    ],
)
def test_report_redacts_paths_and_addresses(private):
    report = issue_reporting.anonymize_report(f'Failed to load "{private}"\nValueError')
    assert private not in report
    assert "ValueError" in report


def test_report_redacts_local_identity(monkeypatch):
    monkeypatch.setattr(issue_reporting.getpass, "getuser", lambda: "privateuser")
    monkeypatch.setattr(
        issue_reporting.socket, "gethostname", lambda: "private-machine"
    )
    report = issue_reporting.anonymize_report(
        "privateuser on private-machine; privateuser@example.org"
    )
    assert "privateuser" not in report
    assert "private-machine" not in report
    assert "example.org" not in report


def test_redaction_failure_omits_private_text(qtbot, monkeypatch):
    def fail():
        raise OSError("Private identity lookup failure")

    monkeypatch.setattr(issue_reporting.socket, "gethostname", fail)
    report = issue_reporting.anonymize_report("Private original error")
    assert "Report redaction failed (OSError)" in report
    assert "Private" not in report
    reports = []
    monkeypatch.setattr(
        error_dialog.IssueReportDialog,
        "exec",
        lambda self: reports.append(self.report_edit.toPlainText()),
    )
    dialog = ErrorDialog(("ValueError", "Private message", "Private traceback"))
    qtbot.addWidget(dialog)
    dialog.open_issue()
    assert "Private" not in reports[0]
    assert "Private traceback" in dialog.display.toPlainText()


def test_diagnostics_are_minimal_and_do_not_reload(monkeypatch):
    def sys_info(*, fid, check_version):
        assert check_version is False
        fid.write('Python: test\nExecutable: "/private/env/python"\n')

    monkeypatch.setattr(issue_reporting.mne, "sys_info", sys_info)
    controller = SimpleNamespace(
        plugins={
            "public_module": SimpleNamespace(__version__="1.2"),
            "private_plugin": SimpleNamespace(),
        },
        _config={
            "plugin_meta": {
                "public_module": {"plugin_type": "module"},
                "private_plugin": {
                    "plugin_type": "path",
                    "script_path": "/private/script.py",
                },
            },
            "selected_inputs": {
                "eeg": ["private-subject"],
                "meg": ["private-run"],
                "ieeg": ["private-session"],
                "subject": ["private-subject"],
                "private-task": ["secret"],
            },
            "bids_dataset_name": "private dataset",
        },
        raw_datatypes=("eeg", "meg", "ieeg"),
        get=lambda *args: pytest.fail("Must not reload config"),
        get_dataset_name=lambda: pytest.fail("Must not scan dataset"),
    )
    report = issue_reporting.collect_diagnostics(controller)
    assert "Python: test" in report
    assert "public_module: 1.2" in report
    assert "custom plugin 2" in report
    assert "- eeg: 1" in report
    assert "- meg: 1" in report
    assert "- ieeg: 1" in report
    assert "private" not in report
    assert "secret" not in report


def test_diagnostic_failures_do_not_obscure_original_error(monkeypatch):
    def fail(**kwargs):
        raise RuntimeError("Private system details")

    monkeypatch.setattr(issue_reporting.mne, "sys_info", fail)
    report = issue_reporting.collect_diagnostics()
    assert "System information unavailable (RuntimeError)" in report
    assert "no active pipeline" in report
    assert "Private" not in report
    report = issue_reporting.collect_diagnostics(SimpleNamespace())
    assert "Pipeline information unavailable" in report


def test_dialog_exports_and_progress(qtbot):
    assert dialogs.ErrorDialog is error_dialog.ErrorDialog
    assert dialogs.AboutDialog.__module__.endswith(".about_dialog")
    assert dialogs.SysInfoMsg.__module__.endswith(".sys_info_msg")
    assert dialogs.ProgressDialog.__module__.endswith(".progress_dialog")
    assert dialogs.show_error_dialog is error_dialog.show_error_dialog
    parent = QWidget()
    qtbot.addWidget(parent)
    about = dialogs.AboutDialog(parent)
    qtbot.addWidget(about)
    progress = ProgressDialog("Loading", maximum=2, parent=parent)
    qtbot.addWidget(progress)
    progress.set_value(2)
    assert progress.progress_bar.value() == 2


def test_sys_info_dialog_still_receives_stdout(qtbot, monkeypatch):
    class StreamSignal(QObject):
        text_written = Signal(str)

    stream = StreamSignal()
    with monkeypatch.context() as context:
        context.setattr("sys.stdout", SimpleNamespace(signal=stream))
        dialog = SysInfoMsg(None)
    qtbot.addWidget(dialog)
    stream.text_written.emit("System info")
    assert dialog.show_widget.toPlainText() == "System info"


def test_show_error_dialog_without_application(monkeypatch):
    monkeypatch.setattr(error_dialog.QApplication, "instance", lambda: None)
    monkeypatch.setattr(
        error_dialog, "ErrorDialog", lambda *args, **kwargs: pytest.fail("No GUI")
    )
    error_dialog.show_error_dialog(("ValueError", "Failed", "Traceback"))
