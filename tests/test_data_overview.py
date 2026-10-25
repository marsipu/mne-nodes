"""Associated empty-room inputs and the recording data overview."""

from threading import Event
from time import perf_counter
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from mne_bids import BIDSPath, get_bids_path_from_fname
from qtpy.QtCore import Qt
from qtpy.QtWidgets import QAbstractItemView

from mne_nodes.backend.code_generation import CodeGenerator
from mne_nodes.backend.data_overview import (
    DataAvailability,
    DataOverview,
    discover_data_overview,
)
from mne_nodes.backend.execution import WorkerSignals
from mne_nodes.gui.data_overview import DataOverviewDialog


@pytest.fixture
def meg_associations(ct):
    """MEG recordings with a real AssociatedEmptyRoom sidecar, without signal data."""
    first = BIDSPath(
        root=ct.bids_root,
        subject="01",
        task="test",
        run="01",
        datatype="meg",
        suffix="meg",
        extension=".fif",
    )
    second = first.copy().update(run="02")
    empty_room = first.copy().update(
        subject="emptyroom", session="20260101", task="noise", run=None
    )
    import json

    for path in (first, second, empty_room):
        path.directory.mkdir(parents=True, exist_ok=True)
        path.fpath.touch()
    for path in (first, second):
        path.copy().update(extension=".json").fpath.write_text(
            json.dumps(
                {
                    "AssociatedEmptyRoom": empty_room.fpath.relative_to(
                        ct.bids_root
                    ).as_posix()
                }
            ),
            encoding="utf-8",
        )
    return first, second, empty_room


def test_empty_room_is_associated_not_selected(ct, meg_associations):
    first, second, empty_room = meg_associations
    assert ct.resolve_empty_room(first) == empty_room
    assert ct.get_datatype_items("emptyroom") == [empty_room.basename]
    assert empty_room.basename not in ct.get_datatype_items("meg")
    assert "emptyroom" not in ct.get_all_datatype_items()
    assert "raw_er" not in ct.get_all_datatype_items()
    ct.input_selection_changed([first.basename, second.basename], "meg")
    assert "raw_er" not in ct.input_output_availability()
    assert ct.selected_recordings() == [first, second]
    assert "emptyroom" not in ct.get_group_by("subject")
    ct.set("selected_inputs", {"emptyroom": [empty_room.basename]})
    ct.discard_legacy_segmentation_checks()
    assert not ct.selected_recordings()


def test_empty_room_missing_mixed_and_non_meg(ct, meg_associations):
    first, second, empty_room = meg_associations
    ct.set("selected_inputs", {})
    assert "raw_er" in ct.input_output_availability()
    ct.input_selection_changed([first.basename], "meg")
    assert "raw_er" not in ct.input_output_availability()
    eeg = ct.get_datatype_items("eeg")[0]
    ct.input_selection_changed([eeg], "eeg")
    assert "participant MEG" in ct.input_output_availability()["raw_er"]
    ct.input_selection_changed([], "eeg")
    empty_room.fpath.unlink()
    assert "raw_er" in ct.input_output_availability()
    with pytest.raises(FileNotFoundError):
        ct.load_raw_er(first)
    empty_room.fpath.touch()
    second.copy().update(extension=".json").fpath.write_text(
        '{"AssociatedEmptyRoom": "sub-emptyroom/meg/sub-emptyroom_task-noise_meg.fif"}',
        encoding="utf-8",
    )
    ct.input_selection_changed([first.basename, second.basename], "meg")
    assert "raw_er" in ct.input_output_availability()


@pytest.mark.parametrize("grouped", [False, True])
def test_load_empty_room_shape_and_recording_independence(
    ct, meg_associations, monkeypatch, grouped
):
    first, second, empty_room = meg_associations
    read = Mock(side_effect=lambda path: ({"path": path}, {}))
    monkeypatch.setattr(ct, "load_raw", read)
    result = ct.load_raw_er([first, second] if grouped else first)
    expected = {"path": empty_room}
    assert result == ([expected, expected] if grouped else expected)
    assert all(call.args == (empty_room,) for call in read.call_args_list)


@pytest.mark.parametrize("target", ["file", "group"])
@pytest.mark.parametrize("empty_first", [False, True])
def test_codegen_routes_empty_room_to_raw_parameters(
    ct, meg_associations, monkeypatch, target, empty_first
):
    """Raw and empty-room streams cannot replace each other through alias matching."""
    first, second, empty_room = meg_associations
    if target == "file":
        ct.set("selected_inputs", {"meg": [first.basename, second.basename]})
    else:
        ct.set("custom_groups", {"recordings": [str(first.fpath), str(second.fpath)]})
        ct.set("selected_inputs", {"custom": ["recordings"]})
    nodes = []
    consumers = {}
    for name, port in (("consume_raw", "meg"), ("consume_noise", "raw_er")):
        meta = {
            "inputs": {"raw": {"accepted_ports": ["raw"]}},
            "outputs": {},
            "parameters": {},
            "class_name": None,
            "plugin": "empty_plugin",
        }
        ct.function_meta[name] = meta
        consumers[name] = Mock()
        nodes.append(
            {
                "name": name,
                "function_meta": meta,
                "inputs": {"raw": ["input"]},
                "input_ports": {"raw": [port]},
                "outputs": {},
                "checked": False,
            }
        )
    if empty_first:
        nodes.reverse()
        meta = {
            "inputs": {"raw": {"accepted_ports": ["raw"]}},
            "outputs": {"raw": {}},
            "parameters": {},
            "class_name": None,
            "plugin": "empty_plugin",
        }
        ct.function_meta["process_noise"] = meta
        consumers["process_noise"] = lambda raw: "processed empty-room"
        nodes.insert(
            1,
            {
                "name": "process_noise",
                "function_meta": meta,
                "inputs": {"raw": ["input"]},
                "input_ports": {"raw": ["raw_er"]},
                "outputs": {"raw": []},
                "checked": False,
            },
        )
    monkeypatch.setattr(
        ct,
        "load_raw",
        lambda items: (
            [path.basename for path in items]
            if isinstance(items, list)
            else items.basename,
            {},
        ),
    )
    monkeypatch.setattr(CodeGenerator, "_build_header", lambda *args: "")
    code = CodeGenerator(ct, {target: nodes}).code
    exec(  # noqa: S102 - Exercise generated pipeline code.
        compile(code, "<empty-room pipeline>", "exec"),
        {
            "ct": ct,
            "get_bids_path_from_fname": get_bids_path_from_fname,
            "empty_plugin": SimpleNamespace(**consumers),
        },
    )
    assert [call.kwargs["raw"] for call in consumers["consume_raw"].call_args_list] == (
        [first.basename, second.basename]
        if target == "file"
        else [[first.basename, second.basename]]
    )
    assert [
        call.kwargs["raw"] for call in consumers["consume_noise"].call_args_list
    ] == (
        [empty_room.basename, empty_room.basename]
        if target == "file"
        else [[empty_room.basename, empty_room.basename]]
    )


def test_conditional_associated_ports_preserve_connections(nodeviewer, monkeypatch):
    node = nodeviewer.input_node
    ct = nodeviewer.ct
    subject = node.output(port_name="subject")
    empty_room = node.output(port_name="raw_er")
    assert not subject.isVisible()
    assert not empty_room.isVisible()
    assert "raw" in empty_room.accepted_ports
    function = nodeviewer.node(node_name="test_filter")
    target = function.input(port_name="raw")
    empty_room.connect_to(target)
    original = ct.get_datatype_items
    available = True

    def items(datatype):
        if datatype in ("subject", "emptyroom"):
            return ["auxiliary-data"] if available else []
        return original(datatype)

    monkeypatch.setattr(ct, "get_datatype_items", items)
    ct.refresh_input_outputs()
    assert subject.isVisible()
    assert empty_room.isVisible()
    assert not empty_room.isEnabled()  # Dataset presence is not a recording selection.
    available = False
    ct.refresh_input_outputs()
    assert not subject.isVisible()
    assert not empty_room.isVisible()
    assert empty_room.connected(target)
    assert node.output(port_name="raw_er") is empty_room
    config = nodeviewer.to_dict()
    nodeviewer.load_nodes(config)
    restored = nodeviewer.input_node.output(port_name="raw_er")
    assert not restored.isVisible()
    assert not restored.isEnabled()
    assert len(restored.connected_ports) == 1
    available = True
    ct.refresh_input_outputs()
    assert restored.isVisible()
    assert len(restored.connected_ports) == 1


def test_empty_room_output_connects_as_raw(nodeviewer, meg_associations):
    first, _second, _empty_room = meg_associations
    ct = nodeviewer.ct
    node = nodeviewer.input_node
    node.update_widgets()
    ct.input_selection_changed([first.basename], "meg")
    output = node.output(port_name="raw_er")
    assert output.isVisible()
    assert output.isEnabled()
    raw_input = nodeviewer.node(node_name="test_filter").input(port_name="raw")
    assert nodeviewer._ports_can_connect(output, raw_input)


def test_data_overview_inventory_and_association_errors(
    ct, meg_associations, monkeypatch
):
    first, _second, empty_room = meg_associations
    for subject in ("sub-01", "unassociated"):
        for folder in ("mri", "surf", "label"):
            (ct.ensure_subjects_dir(False) / subject / folder).mkdir(parents=True)
    anatomy = first.copy().update(
        datatype="anat", task=None, run=None, suffix="T1w", extension=".nii.gz"
    )
    anatomy.directory.mkdir(parents=True, exist_ok=True)
    anatomy.fpath.touch()
    before = ct.get("selected_inputs").copy()
    overview = discover_data_overview(ct)
    assert len(overview.inventory["FreeSurfer"]) == 2
    assert overview.inventory["Empty-room"] == [str(empty_room.fpath)]
    assert overview.inventory["Anatomy"] == [str(anatomy.fpath)]
    meg_rows = [
        row for row in overview.recordings if row["Recording"] == first.basename
    ]
    assert len(meg_rows) == 1
    assert meg_rows[0]["FreeSurfer subject"] == DataAvailability(
        "present", "FreeSurfer subject: sub-01"
    )
    for column, state in (
        ("Anatomy candidates", "present"),
        ("Empty-room", "present"),
        ("Transform", "missing"),
    ):
        availability = meg_rows[0][column]
        assert isinstance(availability, DataAvailability)
        assert availability.state == state
    assert all(row["Recording"] != empty_room.basename for row in overview.recordings)
    assert all(
        isinstance(row["Empty-room"], DataAvailability)
        and row["Empty-room"].state == "not_applicable"
        for row in overview.recordings
        if isinstance(row["Recording"], str) and row["Recording"].endswith("_eeg.vhdr")
    )
    assert ct.get("selected_inputs") == before
    monkeypatch.setattr(
        ct, "resolve_empty_room", Mock(side_effect=ValueError("ambiguous association"))
    )
    overview = discover_data_overview(ct)
    assert any(
        isinstance(row["Empty-room"], DataAvailability)
        and row["Empty-room"].state == "error"
        and "ambiguous association" in row["Empty-room"].description
        for row in overview.recordings
    )


def test_overview_table_and_both_entry_points(main_window, qtbot, monkeypatch):
    window = main_window
    calls = []
    monkeypatch.setattr(
        DataOverviewDialog, "update_widgets", lambda self: calls.append(self)
    )
    action = next(
        action
        for menu_action in window.menuBar().actions()
        if menu_action.menu() and "BIDS" in menu_action.text()
        for action in menu_action.menu().actions()
        if "Data overview" in action.text()
    )
    action.trigger()
    widget = window.viewer.input_node.input_widget
    qtbot.mouseClick(widget.overview_bt, Qt.MouseButton.LeftButton)
    assert len(calls) == 2
    dialog = calls[-1]
    assert dialog.parentWidget() is window.viewer
    assert dialog.graphicsProxyWidget() is None
    assert dialog.isWindow()
    qtbot.waitExposed(dialog)
    overview = discover_data_overview(window.controller)
    dialog._discovered(overview)
    assert dialog.table.model().rowCount() == len(overview.recordings)
    assert dialog.table.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers
    assert "recordings" in dialog.status.text()
    for child in calls:
        child.close()


def test_overview_worker_refresh_and_failure(ct, qtbot, monkeypatch):
    """The actual worker populates the table and errors never resemble success."""
    dialog = DataOverviewDialog(ct)
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.update_widgets()
    qtbot.waitUntil(lambda: dialog._worker is None, timeout=15000)
    assert dialog.table.model().rowCount() == len(ct.get_datatype_items("eeg"))
    assert dialog.refresh_button.isEnabled()
    from mne_nodes.backend.exception_handling import ExceptionTuple

    shown = []
    monkeypatch.setattr(
        "mne_nodes.gui.data_overview.ErrorDialog",
        lambda *args, **kwargs: SimpleNamespace(exec=lambda: shown.append(args)),
    )
    dialog._discovered(ExceptionTuple(ValueError, ValueError("broken scan"), "trace"))
    assert dialog.status.text() == "Dataset scan failed."
    assert dialog.table.model().rowCount() == 0
    assert shown


@pytest.mark.parametrize("empty", [False, True])
def test_overview_discovery_progress(ct, monkeypatch, empty):
    """Discovery switches from busy to counted progress, including empty datasets."""
    if empty:
        monkeypatch.setattr(ct, "get_datatype_items", lambda datatype: [])
    signals = WorkerSignals()
    maxima, values, texts = [], [], []
    signals.pgbar_max.connect(maxima.append)
    signals.pgbar_n.connect(values.append)
    signals.pgbar_text.connect(texts.append)
    overview = discover_data_overview(ct, worker_signals=signals)
    total = len(overview.recordings)
    assert maxima == [0, max(1, total)]
    assert values[0] == 0
    assert values[-1] == max(1, total)
    assert values[1 : 1 + total] == list(range(1, total + 1))
    assert texts[0] == "Discovering anatomy and auxiliary data..."
    assert texts[-1] == f"Scan complete: {total} recordings."
    assert (
        len([text for text in texts if text.startswith("Checking recording")]) == total
    )


def test_overview_worker_shows_recording_progress(ct, qtbot, monkeypatch):
    """The real worker exposes scan progress while an association lookup is running."""
    release = Event()
    resolve = ct.resolve_recording_subject

    def delayed_resolve(recording):
        if not release.wait(10):
            raise RuntimeError("Timed out waiting to release the test scan.")
        return resolve(recording)

    monkeypatch.setattr(ct, "resolve_recording_subject", delayed_resolve)
    dialog = DataOverviewDialog(ct)
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.update_widgets()
    worker = dialog._worker
    try:
        assert worker is not None
        qtbot.waitUntil(
            lambda: worker.progress_label.text().startswith("Checking recording"),
            timeout=5000,
        )
        assert worker.isVisible()
        assert worker.graphicsProxyWidget() is None
        assert worker.progress_bar.isVisible()
        assert worker.progress_bar.maximum() == len(ct.get_datatype_items("eeg"))
        assert worker.progress_bar.value() == 0
        assert not dialog.refresh_button.isEnabled()
        dialog.update_widgets()
        assert dialog._worker is worker
    finally:
        release.set()
        qtbot.waitUntil(lambda: dialog._worker is None, timeout=15000)
    assert dialog.refresh_button.isEnabled()


@pytest.mark.parametrize("state", ["present", "missing", "error", "not_applicable"])
def test_overview_availability_symbols(qtbot, state):
    """Availability is an icon, never a path, with accessible explanations."""
    dialog = DataOverviewDialog(SimpleNamespace(refresh_input_outputs=Mock()))
    qtbot.addWidget(dialog)
    row: dict[str, str | DataAvailability] = {
        column: DataAvailability(state, "Association details")
        for column in dialog.model.columns[1:]
    }
    row["Recording"] = "sub-01_task-test_meg.fif"
    dialog._discovered(DataOverview([row], {}))
    model = dialog.table.model()
    assert model.index(0, 0).data() == row["Recording"]
    for column in range(1, model.columnCount()):
        index = model.index(0, column)
        assert index.data() == ("N/A" if state == "not_applicable" else None)
        assert not index.data(Qt.ItemDataRole.DecorationRole).isNull()
        assert "Association details" in index.data(Qt.ItemDataRole.ToolTipRole)
        assert "Association details" in index.data(Qt.ItemDataRole.AccessibleTextRole)


def test_overview_large_snapshot(qtbot, record_property):
    """Populate and sort 20,000 recordings without building per-cell widgets."""
    controller = SimpleNamespace(refresh_input_outputs=Mock())
    dialog = DataOverviewDialog(controller)
    qtbot.addWidget(dialog)
    available = DataAvailability("present", "Found")
    rows = [
        {
            "Recording": f"sub-{number:05}_task-test_meg.fif",
            **{column: available for column in dialog.model.columns[1:]},
        }
        for number in reversed(range(20000))
    ]
    start = perf_counter()
    dialog._discovered(DataOverview(rows, {}))
    dialog.show()
    qtbot.waitExposed(dialog)
    elapsed = perf_counter() - start
    record_property("overview_20000_rows_seconds", elapsed)
    assert elapsed < 3.0
    assert dialog.model._recordings is rows
    model = dialog.table.model()
    assert model.rowCount() == 20000
    assert model.index(0, 0).data() == "sub-00000_task-test_meg.fif"
    dialog.table.sortByColumn(0, Qt.SortOrder.DescendingOrder)
    assert model.index(0, 0).data() == "sub-19999_task-test_meg.fif"
    controller.refresh_input_outputs.assert_called_once_with()


def test_overview_caches_subject_lookups(ct, meg_associations, monkeypatch):
    """Runs for the same subject reuse lookup results within a scan only."""
    first, second, _empty_room = meg_associations
    resolve = Mock(wraps=ct.resolve_recording_subject)
    monkeypatch.setattr(ct, "resolve_recording_subject", resolve)
    overview = discover_data_overview(ct)
    assert (
        len([call for call in resolve.call_args_list if call.args[0].subject == "01"])
        == 1
    )
    rows = {row["Recording"]: row["FreeSurfer subject"] for row in overview.recordings}
    assert rows[first.basename] is rows[second.basename]
    ct.set("coreg_subjects", {second.basename: "another-subject"})
    resolve.reset_mock()
    discover_data_overview(ct)
    assert (
        len([call for call in resolve.call_args_list if call.args[0].subject == "01"])
        == 2
    )
