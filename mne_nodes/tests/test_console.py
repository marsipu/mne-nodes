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


def test_console_progress_pinning(qtbot):
    """Test progress pinning & finalization with new immediate-finish
    detection.

    Desired semantics:
    - While progress is ongoing (N<M) each update replaces the single bottom line.
    - After final update (N==M or 100%), progress is considered finalized immediately.
      The next normal output should therefore appear *after* the finalized progress line.
    - Additional normal output continues to append normally.
    """
    console = ConsoleWidget()
    qtbot.addWidget(console)
    flush_ms = 20
    console.add_stream("stdout", flush_interval_ms=flush_ms)
    stream = console.get_stream("stdout")

    def wait_for_substring(substr, timeout_s=2.0):
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if substr in console.toPlainText():
                return True
            qtbot.wait(flush_ms)
        return False

    total = 4
    # Emit first three (ongoing) progress updates
    for i in range(1, total):  # 1..3 for total=4
        stream.push(f"\rProgress {i}/{total}")
        assert wait_for_substring(f"Progress {i}/{total}"), "Progress update missing"
        lines = [ln for ln in console.toPlainText().splitlines() if ln.strip()]
        assert lines and lines[-1].endswith(f"Progress {i}/{total}"), (
            "Ongoing progress line not last"
        )

    # Emit final progress update (4/4) which should finalize immediately
    stream.push(f"\rProgress {total}/{total}")
    assert wait_for_substring(f"Progress {total}/{total}"), "Final progress missing"
    lines_after_final = [ln for ln in console.toPlainText().splitlines() if ln.strip()]
    assert lines_after_final and lines_after_final[-1].endswith(
        f"Progress {total}/{total}"
    ), "Final progress should still be last right after emission"

    # First normal output: since progress is finalized, it should appear AFTER the progress line
    stream.push("Normal after progress A\n")
    assert wait_for_substring("Normal after progress A"), "Normal line A missing"
    lines = [ln for ln in console.toPlainText().splitlines() if ln.strip()]
    assert lines[-1].endswith("Normal after progress A"), (
        "Normal line A should be last (progress already finalized)"
    )
    assert any(ln.endswith(f"Progress {total}/{total}") for ln in lines[:-1]), (
        "Progress line should have moved up (no longer last) after normal output"
    )

    # Second normal output: just appends
    stream.push("Normal after progress B\n")
    assert wait_for_substring("Normal after progress B"), "Normal line B missing"
    lines2 = [ln for ln in console.toPlainText().splitlines() if ln.strip()]
    assert lines2[-1].endswith("Normal after progress B"), (
        "Normal line B should be last"
    )
    # Ensure ordering: progress < normal A < normal B somewhere in sequence
    joined = "\n".join(lines2)
    assert (
        joined.index(f"Progress {total}/{total}")
        < joined.index("Normal after progress A")
        < joined.index("Normal after progress B")
    ), "Ordering of finalized progress and subsequent lines incorrect"


def test_console_progress_heavy_interleaved(qtbot):
    """Stress test progress pinning with heavy interleaved normal output.

    Scenario:
    - Multiple progress updates (N/Total) each followed by bursts of normal lines.
    - Some progress updates include trailing descriptive text and newline-packed
      chunks to mimic real-world mixed writes (progress + normal output in one push).
    - Verify: while progress < final, the LAST non-empty line is always the current
      progress state. After final progress (N==Total) the progress line is
      finalized and subsequent normal lines appear beneath it.
    """
    console = ConsoleWidget()
    qtbot.addWidget(console)
    flush_ms = 15
    console.add_stream("stdout", flush_interval_ms=flush_ms)
    stream = console.get_stream("stdout")

    total = 8
    burst = 15  # normal lines per step

    def wait_cond(pred, timeout_s=3.0):
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if pred():
                return True
            qtbot.wait(flush_ms)
        return False

    def last_line():
        lines = [ln for ln in console.toPlainText().splitlines() if ln.strip()]
        return lines[-1] if lines else ""

    # Emit progress steps 1..(total-1) interleaved with normal output
    for step in range(1, total):
        # Mixed chunk: progress + description + newline + a normal line
        stream.push(
            f"\r{step}/{total} processing step {step}\nfirst normal after {step}\n"
        )
        # Additional burst of normal lines
        for j in range(burst):
            stream.push(f"normal {step}-{j}\n")
        # Wait until progress token visible
        assert wait_cond(lambda s=step: f"{s}/{total}" in console.toPlainText()), (
            f"Progress {step}/{total} not found in time"
        )
        # Ensure last line ends with progress fragment (progress pinned at bottom)
        assert f"{step}/{total}" in last_line(), (
            f"Active progress {step}/{total} not last line. Last line: '{last_line()}'"
        )

    # Final progress update (should finalize)
    stream.push(
        f"\r{total}/{total} finalizing step {total}\npost-final normal inline\n"
    )
    assert wait_cond(lambda: f"{total}/{total}" in console.toPlainText()), (
        "Final progress missing"
    )
    # While immediately after emission, last line should still be the final progress (before extra lines)
    assert f"{total}/{total}" in last_line(), (
        "Final progress line not last right after emission"
    )

    # Push extra normal lines after finalization
    for k in range(5):
        stream.push(f"after-final {k}\n")
    assert wait_cond(lambda: "after-final 4" in console.toPlainText()), (
        "Post-final lines missing"
    )

    final_text = console.toPlainText().splitlines()
    non_empty = [ln for ln in final_text if ln.strip()]
    # Last line should be the last after-final line
    assert non_empty[-1].endswith("after-final 4"), "After-final line not last"
    # Progress final line should appear somewhere before the trailing lines
    progress_indices = [i for i, ln in enumerate(non_empty) if f"{total}/{total}" in ln]
    assert progress_indices, "Final progress line not found in accumulated text"
    assert progress_indices[-1] < len(non_empty) - 1, (
        "Final progress line still last after subsequent normal output"
    )
