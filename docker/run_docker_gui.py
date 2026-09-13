"""Launch MNE-Nodes from Docker on the host X11 display."""

import argparse
import os
import platform
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMAGE = "mne-nodes:local"


def run(command: list[str]) -> None:
    """Run a command and return its exit code to the caller on failure."""
    result = subprocess.run(command, check=False)
    if result.returncode:
        raise SystemExit(result.returncode)


def vcxsrv_is_running() -> bool:
    """Return whether VcXsrv is already running on Windows."""
    result = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq vcxsrv.exe", "/NH"],
        capture_output=True,
        check=False,
    )
    return b"vcxsrv.exe" in result.stdout.lower()


def start_vcxsrv() -> None:
    """Start VcXsrv in multi-window mode when available."""
    if vcxsrv_is_running():
        return

    candidates = [
        Path(os.environ.get("ProgramFiles", "")) / "VcXsrv" / "vcxsrv.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "VcXsrv" / "vcxsrv.exe",
    ]
    executable = next((path for path in candidates if path.is_file()), None)
    if executable is None:
        raise SystemExit(
            "VcXsrv is not running or installed. Install it, start XLaunch on "
            "display 0 in multi-window mode, or use --no-start-x-server."
        )
    subprocess.Popen([str(executable), ":0", "-multiwindow", "-ac"])


def grant_x_access(system: str) -> list[str] | None:
    """Permit the container to use the host X server and return its cleanup command."""
    if shutil.which("xhost") is None:
        raise SystemExit("xhost is required to grant Docker access to the X server.")

    if system == "Linux":
        run(["xhost", "+si:localuser:root"])
        return ["xhost", "-si:localuser:root"]

    run(["xhost", "+localhost"])
    return ["xhost", "-localhost"]


def docker_command(system: str) -> list[str]:
    """Build the Docker command for the current host platform."""
    command = ["docker", "run", "--rm", "-e", "QT_X11_NO_MITSHM=1"]
    if system == "Windows":
        command.extend(["-e", "DISPLAY=host.docker.internal:0.0"])
    elif system == "Linux":
        display = os.environ.get("DISPLAY")
        if not display:
            raise SystemExit("DISPLAY is not set. Run this from an active X11 session.")
        if not Path("/tmp/.X11-unix").is_dir():
            raise SystemExit(
                "The host X11 socket directory /tmp/.X11-unix is unavailable."
            )
        command.extend(
            ["-e", f"DISPLAY={display}", "-v", "/tmp/.X11-unix:/tmp/.X11-unix:rw"]
        )
    elif system == "Darwin":
        command.extend(["-e", "DISPLAY=host.docker.internal:0"])
    else:
        raise SystemExit(f"Unsupported operating system: {system}")
    return [*command, IMAGE]


def image_exists() -> bool:
    """Return whether the Docker image required by the launcher is available."""
    result = subprocess.run(
        ["docker", "image", "inspect", IMAGE], capture_output=True, check=False
    )
    return result.returncode == 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-start-x-server",
        action="store_true",
        help="Do not automatically start VcXsrv on Windows.",
    )
    arguments = parser.parse_args()

    system = platform.system()
    if not image_exists():
        raise SystemExit(
            f"Docker image '{IMAGE}' is unavailable. Build it with "
            "'python docker/build_docker_image.py'."
        )

    if system == "Windows" and not arguments.no_start_x_server:
        start_vcxsrv()

    cleanup_command = None
    if system in {"Linux", "Darwin"}:
        cleanup_command = grant_x_access(system)

    try:
        run(docker_command(system))
    finally:
        if cleanup_command is not None:
            subprocess.run(cleanup_command, check=False)


if __name__ == "__main__":
    main()
