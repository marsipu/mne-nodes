"""Audit function-node construction in isolated subprocesses.

This script iterates over all registered MNE function nodes, creates each node
in a fresh subprocess, and records any failures in a markdown report.
"""

from __future__ import annotations

import argparse
import faulthandler
import json
import os
import subprocess
import sys
import tempfile
import traceback
from collections.abc import Sequence
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from tqdm import tqdm


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _development_dir() -> Path:
    return Path(__file__).resolve().parent


def _tiny_bids_root() -> Path:
    return _repo_root() / "mne_nodes" / "tests" / "tiny_bids"


def _config_path_for_run(run_dir: Path) -> Path:
    return run_dir / "function_node_audit_config.json"


def _create_config_file(config_path: Path) -> None:
    from mne_nodes.pipeline.controller import default_config
    from mne_nodes.pipeline.io import TypedJSONEncoder

    config = deepcopy(default_config)
    config["name"] = "function-node-audit"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as file:
        json.dump(config, file, indent=4, cls=TypedJSONEncoder)


def _create_controller(run_dir: Path):
    from mne_nodes.pipeline.controller import Controller
    from mne_nodes.pipeline.settings import Settings

    settings_dir = run_dir / "settings"
    settings_dir.mkdir(parents=True, exist_ok=True)
    os.environ["MNENODES_SETTINGS_DIR"] = str(settings_dir)

    settings = Settings()
    settings.set("bids_root", _tiny_bids_root())

    config_path = _config_path_for_run(run_dir)
    _create_config_file(config_path)

    return Controller(config_path=config_path, settings=settings)


def _normalize_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _worker(function_name: str) -> int:
    faulthandler.enable()
    os.environ["MNENODES_DEBUG"] = "true"

    from qtpy.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])

    controller = _create_controller(
        Path(tempfile.mkdtemp(prefix="mnenodes-node-audit-"))
    )

    # Import the heavy GUI pieces only after QApplication exists.
    from mne_nodes.gui.node.node_viewer import NodeViewer

    viewer = None
    node = None
    try:
        viewer = NodeViewer(controller)
        node = viewer.add_function_node(function_name)
        app.processEvents()
        return 0
    except Exception:
        traceback.print_exc()
        return 1
    finally:
        if node is not None:
            try:
                if viewer is not None:
                    viewer.remove_node(node)
            except Exception:
                traceback.print_exc()
        if viewer is not None:
            try:
                viewer.close()
                viewer.deleteLater()
            except Exception:
                traceback.print_exc()
        app.processEvents()


def _available_function_names() -> list[str]:
    controller = _create_controller(
        Path(tempfile.mkdtemp(prefix="mnenodes-node-audit-list-"))
    )
    return sorted(controller.function_meta)


def _render_markdown(
    *,
    report_path: Path,
    function_names: Sequence[str],
    passed: Sequence[str],
    failures: Sequence[dict[str, str]],
    timeout: int,
) -> str:
    lines: list[str] = []
    lines.append("# Function Node Audit Report")
    lines.append("")
    lines.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"Report path: {report_path}")
    lines.append(f"Timeout per function: {timeout}s")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Total functions: {len(function_names)}")
    lines.append(f"- Passed: {len(passed)}")
    lines.append(f"- Failed: {len(failures)}")
    lines.append("")

    if failures:
        lines.append("## Failed Functions")
        lines.append("")
        for failure in failures:
            lines.append(f"### {failure['function_name']}")
            lines.append("")
            lines.append(f"- Return code: {failure['returncode']}")
            lines.append(f"- Reason: {failure['reason']}")
            if failure.get("stdout"):
                lines.append("")
                lines.append("#### Stdout")
                lines.append("")
                lines.append("```text")
                lines.append(failure["stdout"].rstrip())
                lines.append("```")
            if failure.get("stderr"):
                lines.append("")
                lines.append("#### Stderr")
                lines.append("")
                lines.append("```text")
                lines.append(failure["stderr"].rstrip())
                lines.append("```")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run each MNE function node in an isolated subprocess and write a "
            "markdown report with failures."
        )
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=_development_dir() / "function_node_audit_report.md",
        help="Path to the markdown report to write.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Timeout in seconds for each subprocess worker.",
    )
    parser.add_argument("--worker", type=str, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.worker is not None:
        return _worker(args.worker)

    faulthandler.enable()

    function_names = _available_function_names()
    passed: list[str] = []
    failures: list[dict[str, str]] = []
    worker_script = Path(__file__).resolve()
    report_path = args.report.resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)

    with tqdm(total=len(function_names), desc="Function nodes", unit="func") as bar:
        for function_name in function_names:
            try:
                result = subprocess.run(
                    [sys.executable, str(worker_script), "--worker", function_name],
                    cwd=str(_repo_root()),
                    capture_output=True,
                    text=True,
                    timeout=args.timeout,
                )
            except subprocess.TimeoutExpired as err:
                failures.append(
                    {
                        "function_name": function_name,
                        "returncode": "timeout",
                        "reason": f"Subprocess timed out after {args.timeout}s.",
                        "stdout": _normalize_output(err.stdout),
                        "stderr": _normalize_output(err.stderr),
                    }
                )
            else:
                if result.returncode == 0:
                    passed.append(function_name)
                else:
                    stderr = (result.stderr or "").strip()
                    stdout = (result.stdout or "").strip()
                    reason = stderr or stdout or "No output captured."
                    failures.append(
                        {
                            "function_name": function_name,
                            "returncode": str(result.returncode),
                            "reason": reason,
                            "stdout": stdout,
                            "stderr": stderr,
                        }
                    )
            finally:
                bar.update(1)

    report = _render_markdown(
        report_path=report_path,
        function_names=function_names,
        passed=passed,
        failures=failures,
        timeout=args.timeout,
    )
    report_path.write_text(report, encoding="utf-8")
    print(f"Wrote report to {report_path}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(_main())
