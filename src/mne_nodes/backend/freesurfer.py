"""FreeSurfer subject import and isolated native/WSL execution."""

import pickle
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from inspect import unwrap
from pathlib import Path, PureWindowsPath
from tempfile import TemporaryDirectory
from typing import Any

from mne_nodes import iswin
from mne_nodes.backend.execution import WorkerSignals


def is_freesurfer_subject(path: Path) -> bool:
    """Return whether a folder has the subject structure used by MNE-Nodes."""
    return all((path / name).is_dir() for name in ("mri", "surf", "label"))


def find_freesurfer_subjects(source: Path) -> list[Path]:
    """List subject folders directly inside an existing subjects directory."""
    if not source.is_dir():
        raise NotADirectoryError(
            f"FreeSurfer source directory does not exist: {source}"
        )
    return sorted(
        (path for path in source.iterdir() if is_freesurfer_subject(path)),
        key=lambda path: path.name,
    )


def import_freesurfer_subjects(
    sources: list[Path], destination: Path, worker_signals: WorkerSignals
) -> list[Path]:
    """Copy subjects without overwriting existing data or exposing partial subjects.

    Each subject is staged inside the destination filesystem before being renamed.
    Cancellation takes effect between subjects. Completed subjects are retained if
    a later copy fails; the failed subject's temporary copy is cleaned up.
    """
    if not sources:
        raise ValueError("Select at least one FreeSurfer subject to import.")
    destination = destination.resolve()
    targets = {destination / source.name for source in sources}
    if len(targets) != len(sources):
        raise ValueError("Selected subjects must have unique folder names.")
    for source in sources:
        if not is_freesurfer_subject(source):
            raise ValueError(f"Expected mri, surf and label directories in {source}.")
        resolved = source.resolve()
        if destination.is_relative_to(resolved) or resolved.is_relative_to(destination):
            raise ValueError(f"Source and destination must not overlap: {source}.")
        target = destination / source.name
        if target.exists() or target.is_symlink():
            raise FileExistsError(
                f"Subject already exists: {target}. No existing subjects were replaced."
            )
    destination.mkdir(parents=True, exist_ok=True)
    worker_signals.pgbar_max.emit(len(sources))
    imported = []
    for number, source in enumerate(sources, 1):
        if worker_signals.was_canceled:
            break
        worker_signals.pgbar_text.emit(f"Copying FreeSurfer subject: {source.name}")
        with TemporaryDirectory(
            prefix=".mne-nodes-import-", dir=destination
        ) as staging:
            staged = Path(staging) / source.name
            shutil.copytree(source, staged)
            # Do not publish an incomplete or canceled subject as a usable import.
            if worker_signals.was_canceled:
                break
            target = destination / source.name
            if target.exists() or target.is_symlink():
                raise FileExistsError(f"Subject appeared during import: {target}.")
            staged.rename(target)
        imported.append(target)
        worker_signals.pgbar_n.emit(number)
    return imported


_DISCOVER = r"""
set -e
python=$1
fs=${FREESURFER_HOME:-}
if [ -z "$fs" ]; then
    if command -v recon-all >/dev/null 2>&1; then
        fs=$(cd "$(dirname "$(command -v recon-all)")/.." && pwd -P)
    fi
    if [ -z "$fs" ]; then
        for root in /usr/local/freesurfer /opt/freesurfer /Applications/freesurfer; do
            if [ -f "$root/SetUpFreeSurfer.sh" ]; then
                fs=$root
                break
            fi
            for candidate in "$root"/*; do
                if [ -f "$candidate/SetUpFreeSurfer.sh" ]; then fs=$candidate; fi
            done
            if [ -n "$fs" ]; then break; fi
        done
    fi
fi
if [ ! -f "$fs/SetUpFreeSurfer.sh" ]; then
    echo "FreeSurfer not found. Install FreeSurfer or set FREESURFER_HOME in your shell." >&2
    exit 2
fi
printf '\nMNE_NODES_FS=%s\n' "$fs"
if [ -n "$python" ]; then
    "$python" -c 'import mne' >&2
else
    candidates="$(command -v python 2>/dev/null || true)
$(command -v python3 2>/dev/null || true)"
    if [ -f "$HOME/.conda/environments.txt" ]; then
        while IFS= read -r env; do candidates="$candidates
$env/bin/python"; done < "$HOME/.conda/environments.txt"
    fi
    for root in "$HOME/miniconda3" "$HOME/anaconda3" "$HOME/miniforge3" /opt/conda; do
        candidates="$candidates
$root/bin/python"
        for env in "$root"/envs/*; do candidates="$candidates
$env/bin/python"; done
    done
    while IFS= read -r candidate; do
        if [ -x "$candidate" ] && "$candidate" -c 'import mne' >/dev/null 2>&1; then
            python=$candidate
            break
        fi
    done <<< "$candidates"
fi
printf 'MNE_NODES_PYTHON=%s\n' "$python"
"""

_SETUP = r"""
set -e
export FREESURFER_HOME=$1
subjects=$2
shift 2
source "$FREESURFER_HOME/SetUpFreeSurfer.sh" >&2
export SUBJECTS_DIR=$subjects
exec "$@"
"""


@dataclass(frozen=True)
class FreeSurferRuntime:
    """Discovered paths in the execution OS, not necessarily the host OS."""

    fs_path: str
    python: str | None
    distribution: str | None = None


def _wsl_prefix(distribution: str | None) -> list[str]:
    return [
        "wsl.exe",
        *(["--distribution", distribution] if distribution else []),
        "--exec",
    ]


def _capture(command: list[str]) -> str:
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            f"FreeSurfer setup failed ({result.returncode}):\n"
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    return result.stdout.strip()


def discover_freesurfer(distribution: str | None = None) -> FreeSurferRuntime:
    """Find FreeSurfer and a Python with MNE from the execution environment.

    Discovery is read-only. The interactive login shell supplies the same
    environment as a terminal, including .bashrc/Conda/FS_LICENSE on WSL.
    Standard installation locations are a fallback, not required settings.
    Linux/macOS use the current interpreter for Python calls.
    """
    prefix = _wsl_prefix(distribution) if iswin else []
    python = "" if iswin else sys.executable
    output = _capture([*prefix, "bash", "-lic", _DISCOVER, "mne-nodes", python])
    fields = dict(re.findall(r"^MNE_NODES_(FS|PYTHON)=(.*)$", output, re.MULTILINE))
    if not fields.get("FS"):
        raise RuntimeError(f"FreeSurfer discovery returned no installation:\n{output}")
    return FreeSurferRuntime(fields["FS"], fields.get("PYTHON") or None, distribution)


def _linux_path(value: str | Path, distribution: str | None) -> str:
    text = str(value)
    if PureWindowsPath(text).is_absolute():
        return _capture([*_wsl_prefix(distribution), "wslpath", "-a", "-u", text])
    return text


def stream_subprocess(command: Sequence[str]) -> None:
    """Stream all merged output and raise on a nonzero exit status."""
    with subprocess.Popen(
        list(command),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    ) as process:
        if process.stdout is None:
            raise RuntimeError("Subprocess output pipe was not created.")
        for line in process.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
        returncode = process.wait()
    if returncode:
        raise subprocess.CalledProcessError(returncode, list(command))


def run_freesurfer_subprocess(
    command: Sequence[str | Path],
    subjects_dir: str | Path,
    *,
    distribution: str | None = None,
    runtime: FreeSurferRuntime | None = None,
) -> None:
    """Run argv after sourcing FreeSurfer in an isolated bash/WSL child.

    Arguments are never interpolated into shell code or modified in place.
    Windows absolute paths are translated by wslpath, including UNC paths.
    No MNE interpreter is required to run an executable such as recon-all.
    """
    if isinstance(command, (str, bytes)) or not command:
        raise ValueError("Command must be a nonempty argument sequence, not a string.")
    runtime = runtime or discover_freesurfer(distribution=distribution)
    argv = [str(arg) for arg in command]
    directory = str(subjects_dir)
    prefix = []
    if iswin:
        prefix = _wsl_prefix(runtime.distribution)
        directory = _linux_path(directory, runtime.distribution)
        argv = [_linux_path(arg, runtime.distribution) for arg in argv]
    stream_subprocess(
        [
            *prefix,
            "bash",
            "-lic",
            _SETUP,
            "mne-nodes",
            runtime.fs_path,
            directory,
            *argv,
        ]
    )


def run_freesurfer_function(
    function: Callable[..., Any],
    kwargs: dict[str, Any],
    subjects_dir: str | Path,
    *,
    runtime: FreeSurferRuntime,
) -> Any:
    """Execute an importable Python function in the FreeSurfer child environment.

    Trusted, private temporary pickle files preserve MNE/numpy results. The
    child Python must have compatible dependencies and the function's module
    installed. Qt objects, closures and live GUI state must not be passed.
    """
    from mne_nodes.backend._freesurfer_worker import PathPickler

    function = unwrap(function)
    if "<locals>" in function.__qualname__:
        raise ValueError(
            "FreeSurfer functions must be importable module-level callables."
        )
    if not runtime.python:
        raise RuntimeError(
            "No Python with MNE was found in WSL. Install MNE in a Linux Conda "
            "environment. Activate it in your WSL shell startup to prioritize it."
        )

    def translate(path: str) -> str:
        return _linux_path(path, runtime.distribution) if iswin else path

    def translate_values(value: Any) -> Any:
        if isinstance(value, str) and iswin and PureWindowsPath(value).is_absolute():
            return translate(value)
        if isinstance(value, dict):
            return {key: translate_values(item) for key, item in value.items()}
        if isinstance(value, (tuple, list)):
            return type(value)(translate_values(item) for item in value)
        return value

    worker = Path(__file__).with_name("_freesurfer_worker.py")
    with TemporaryDirectory(prefix="mne-nodes-freesurfer-") as directory:
        request = Path(directory) / "request.pkl"
        response = Path(directory) / "response.pkl"
        with request.open("wb") as stream:
            PathPickler(stream, translate).dump(
                (function.__module__, function.__qualname__, translate_values(kwargs))
            )
        run_freesurfer_subprocess(
            [
                runtime.python,
                "-u",
                worker,
                request,
                response,
                "wsl" if iswin else "native",
            ],
            subjects_dir,
            runtime=runtime,
        )
        with response.open("rb") as stream:
            return pickle.load(stream)
