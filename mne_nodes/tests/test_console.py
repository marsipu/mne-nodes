"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import logging
import os
import time
import traceback

from mne_nodes.__main__ import init_streams, init_logging
from mne_nodes.gui.console import MainConsoleWidget, ConsoleWidget


def test_logging(qtbot):
    """Test streaming and logging to GUI-Console.

    Also verify that a real exception traceback reaches the stderr
    stream.
    """
    # Enable debugging
    os.environ["MNENODES_DEBUG"] = "true"

    init_streams()
    init_logging()

    console = MainConsoleWidget()
    qtbot.addWidget(console)

    wait_time = console.buffer_time * 2

    # stdout: plain print
    print("Print-Test")
    qtbot.wait(wait_time)
    assert "Print-Test" in console.toPlainText()

    # stderr: real exception with traceback to stderr
    try:
        raise RuntimeError("Test-Error")
    except RuntimeError:
        # This prints a full traceback to sys.stderr (hooked by our console)
        traceback.print_exc()

    # Wait until traceback header and error message appear or timeout
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        text = console.toPlainText()
        if (
            "Traceback (most recent call last):" in text
            and "RuntimeError: Test-Error" in text
        ):
            break
        qtbot.wait(wait_time)
    text = console.toPlainText()
    assert "Traceback (most recent call last):" in text
    assert "RuntimeError: Test-Error" in text

    # logging -> by default logging.StreamHandler uses sys.stderr
    logging.info("Logging-Test")
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        if "[INFO] Logging-Test" in console.toPlainText():
            break
        qtbot.wait(wait_time)
    assert "[INFO] Logging-Test" in console.toPlainText()


def test_console_stream_basic(qtbot):
    """Set up a ConsoleWidget and write via streams (bytes and str)."""
    console = ConsoleWidget()
    qtbot.addWidget(console)
    # Faster flush for test speed
    console.add_stream("stdout", flush_interval_ms=20)

    # Push bytes and strings
    console.get_stream("stdout").push(b"Hello from bytes\n")
    console.get_stream("stdout").push(" and text!\n")

    qtbot.wait(100)
    text = console.toPlainText()
    assert "Hello from bytes" in text
    assert "and text!" in text


def test_console_stress_batching_and_timing(qtbot):
    """Stress test batching and collect simple timing metrics.

    - Push many small chunks and ensure appendHtml calls are far fewer than chunks.
    - Compare times for appending large preformatted HTML vs decoding+formatting a large bytes blob.
    """
    console = ConsoleWidget()
    qtbot.addWidget(console)
    flush_ms = 20
    console.add_stream("stdout", flush_interval_ms=flush_ms)

    # Monkeypatch appendHtml to count calls
    append_calls = {"count": 0}
    original_append = console.appendHtml

    def patched_append(html):
        append_calls["count"] += 1
        return original_append(html)

    # Patch instance method
    console.appendHtml = patched_append  # type: ignore[assignment]

    # Stress: push many small chunks quickly
    N = 2000
    for i in range(N):
        console.get_stream("stdout").push(f"line {i}\n")

    # Wait until last line appears or timeout
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if f"line {N - 1}" in console.toPlainText():
            break
        qtbot.wait(20)

    # Basic sanity: all data surfaced
    assert f"line {N - 1}" in console.toPlainText()
    # Batching sanity: appendHtml must be significantly fewer than N
    # Allow a generous threshold to avoid flakiness on slow CI
    assert append_calls["count"] <= max(50, N // 5)

    # Benchmark: large appendHtml vs large decode/format
    # Build a moderately large payload (~1 MB)
    lines = 20000
    large_text = "\n".join(["x" * 50 for _ in range(lines)])
    large_html = (
        large_text.replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
    )

    # Measure appendHtml path directly
    t0 = time.monotonic()
    console.write_html(large_html)
    # Give the event loop a chance to render
    qtbot.wait(50)
    t_append = time.monotonic() - t0

    # Measure decode/format path on a fresh console
    console2 = ConsoleWidget()
    qtbot.addWidget(console2)
    console2.add_stream("stdout", flush_interval_ms=flush_ms)

    t1 = time.monotonic()
    console2.get_stream("stdout").push(large_text.encode("utf-8"))

    # Wait for presence of a sentinel substring
    sentinel = "x" * 50
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if sentinel in console2.toPlainText():
            break
        qtbot.wait(20)
    t_decode = time.monotonic() - t1

    # Both operations should complete within a reasonable time budget.
    # We avoid tight thresholds due to CI variability.
    assert t_append < 2.0
    assert t_decode < 2.5

    # Optional: log timings to test output for visibility
    print(
        f"appendHtml(~{lines} lines) took {t_append:.3f}s; decode+format took {t_decode:.3f}s"
    )
