"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

from __future__ import annotations

import sys

import pytest

from mne_nodes.__main__ import init_streams, init_logging
from mne_nodes.gui.console import ConsoleWidget
from mne_nodes.pipeline.execution import ProcessDialog, Process


def test_process(qtbot):
    console = ConsoleWidget()
    qtbot.addWidget(console)
    console.show()
    commands = f"{sys.executable} -c \"import sys; print('TEST_OUT'); print('TEST_ERR', file=sys.stderr)\""
    process = Process(commands, console=console, self_destruct=False)
    process.start()
    qtbot.wait(1000)
    console_text = console.toPlainText()
    # Assertions on output presence
    assert "TEST_OUT" in console_text, "Stdout not captured in console"
    assert "TEST_ERR" in console_text, "Stderr not captured in console"


@pytest.mark.timeout(10)
def test_main_window_process_execution(qtbot, main_window, controller, tmp_path):
    """Test launching a process through Controller/MainWindow integration.

    Uses a trivial Python one-shot command that writes to stdout &
    stderr.
    """
    console = main_window.console_dock.add_process()
    commands = f"{sys.executable} -c \"import sys; print('MW_OUT'); print('MW_ERR', file=sys.stderr)\""
    process = controller.create_process(
        commands,
        working_directory=controller.data_path,
        console=console,
        self_destruct=False,
    )

    # Start and wait for finish
    process.start()

    # Allow event loop a moment to flush final console batches
    qtbot.wait(1000)

    # Retrieve console text
    console_text = process.console.toPlainText()

    # Assertions on output presence
    assert "MW_OUT" in console_text, "Stdout not captured in console"
    assert "MW_ERR" in console_text, "Stderr not captured in console"

    # Controller bookkeeping
    assert process.state() == 0


@pytest.mark.timeout(10)
def test_qprocess_dialog_execution(qtbot, controller):
    """Test a QProcessDialog that registers with the Controller.

    Ensures dialog execution finishes, output is captured, and
    controller stores process.
    """
    # Ensure global stream redirection is active for MainConsoleWidget inside dialog
    init_streams()
    init_logging(debug_mode=True)
    py_snippet = "import sys; print('DIALOG_OUT'); print('DIALOG_ERR', file=sys.stderr)"
    commands = [[sys.executable, "-c", py_snippet]]

    dialog = ProcessDialog(
        commands=commands,
        show_buttons=False,
        show_console=True,
        close_directly=False,
        blocking=False,
        controller=controller,
    )
    qtbot.addWidget(dialog)

    assert dialog.process is not None, "Dialog did not initialize worker"
    assert dialog.proc_idx is not None, (
        "Dialog did not register process with controller"
    )

    # Wait for completion
    with qtbot.waitSignal(dialog.process.finished, timeout=5000):
        pass

    # Let console flush
    qtbot.wait(100)
    console_text = dialog.console.toPlainText()
    assert "DIALOG_OUT" in console_text, "Dialog stdout missing"
    assert "DIALOG_ERR" in console_text, "Dialog stderr missing"

    # Controller should track the process
    meta = controller.process(dialog.proc_idx)
    assert meta["status"] == "finished"
    assert meta.get("exit_code", 0) == 0

    # Do NOT explicitly close here; qtbot teardown will handle it safely.


def test_functionnode_start(monkeypatch, main_window, controller):
    # Capture instructions instead of spawning a process
    captured = {}

    def fake_start(instructions, start_name):  # noqa: ARG001
        captured["instructions"] = instructions
        captured["start_name"] = start_name

    monkeypatch.setattr(controller, "start", fake_start)

    viewer = main_window.viewer

    # Ensure input node exists
    input_node = viewer.input_node("raw")

    def ensure_function(name):
        try:
            return viewer.function_node(name)
        except KeyError:
            return viewer.add_function_node(name)

    f_filter = ensure_function("filter_data")
    f_find = ensure_function("find_events")
    f_epoch = ensure_function("epoch_raw")
    f_plot = (
        ensure_function("plot_epochs")
        if "plot_epochs" in controller.function_metas
        else None
    )

    # Helper to connect ports if not already connected
    def connect(out_node, out_port, in_node, in_port):
        oport = out_node.output(port_name=out_port)
        iport = in_node.input(port_name=in_port)
        if iport not in oport.connected_ports:
            oport.connect_to(iport)

    # Build minimal dependency graph if missing
    connect(input_node, "raw", f_filter, "raw")
    connect(input_node, "raw", f_find, "raw")
    # find_events -> epoch_raw (events)
    if f_epoch.input(port_name="events") and f_find.output(port_name="events"):
        connect(f_find, "events", f_epoch, "events")
    # filter_data -> epoch_raw (raw)
    connect(f_filter, "raw", f_epoch, "raw")
    # epoch_raw -> plot_epochs (epochs)
    if (
        f_plot
        and f_epoch.output(port_name="epochs")
        and f_plot.input(port_name="epochs")
    ):
        connect(f_epoch, "epochs", f_plot, "epochs")

    # Start from epoch_raw function node
    f_epoch.start()

    assert "instructions" in captured, "Controller.start was not invoked."
    instr = captured["instructions"]
    # First instruction must be an Input
    assert instr[0][1] == "Input"

    # Extract function order
    func_order = [name for name, kind in instr if kind == "Function"]
    # Required dependencies
    for dep in ("filter_data", "find_events", "epoch_raw"):
        assert dep in func_order
    # Dependencies must appear before epoch_raw
    idx_epoch = func_order.index("epoch_raw")
    assert func_order.index("filter_data") < idx_epoch
    assert func_order.index("find_events") < idx_epoch
    # Downstream function (plot_epochs) should appear after epoch_raw if present
    if "plot_epochs" in func_order:
        assert idx_epoch < func_order.index("plot_epochs")


def test_inputnode_start(monkeypatch, qtbot, main_window, controller):
    # Ensure at least one dummy subject so generated loop has iteration
    if "dummy_subj" not in controller.inputs["raw"]["All"]:
        controller.inputs["raw"]["All"].append("dummy_subj")
        controller.selected_inputs.append("dummy_subj")

    SENTINEL = "PIPELINE_START_SENTINEL"

    def fake_convert(instructions, start_name):  # noqa: ARG001
        return f"print('{SENTINEL}')\n"

    monkeypatch.setattr(controller, "convert_to_code", fake_convert)

    input_node = main_window.viewer.input_node(data_type="raw")

    input_node.start()

    proc_idx = max(controller._process_info.keys())
    worker = controller.process(proc_idx)
    assert worker is not None, "Worker not stored in controller."

    with qtbot.waitSignal(worker.finished, timeout=5000):
        pass

    # Allow console flush
    qtbot.wait(100)

    proc_tabs = main_window.console_dock.process_tabs
    console_text = ""
    if proc_idx in proc_tabs:
        console_text = proc_tabs[proc_idx]["console"].toPlainText()

    assert SENTINEL in console_text, "Sentinel output not found in console."
    meta = controller.process(proc_idx)
    assert meta["status"] == "finished"
    assert meta.get("exit_code", 0) == 0
