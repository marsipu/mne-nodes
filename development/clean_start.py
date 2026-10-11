"""Run MNE-Nodes as if it were started for the first time.

The app uses a temporary settings directory, so the real settings file is never
touched. Other persistent state in the home directory (``~/.mne-nodes`` and
``~/mne_nodes.log``) is backed up before the start and restored after the app
closes. Additional command-line arguments are passed on to MNE-Nodes.

Close any existing MNE-Nodes instances before running this script:
    conda run -n mnedev python development/clean_start.py
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SRC_PATH = Path(__file__).resolve().parents[1] / "src"
HOME_STATE = [Path.home() / ".mne-nodes", Path.home() / "mne_nodes.log"]


def _remove(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def _copy(source: Path, destination: Path) -> None:
    if source.is_dir():
        shutil.copytree(source, destination)
    else:
        shutil.copy2(source, destination)


def main() -> int:
    """Start MNE-Nodes with fresh state and restore the previous state on exit."""
    with tempfile.TemporaryDirectory(prefix="mne-nodes-fresh-") as temp_dir:
        temp_path = Path(temp_dir)
        backup_dir = temp_path / "backup"
        backup_dir.mkdir()

        backups = {}
        for path in HOME_STATE:
            if path.exists():
                backups[path] = backup_dir / path.name
                _copy(path, backups[path])
                _remove(path)

        env = os.environ.copy()
        env["MNENODES_SETTINGS_DIR"] = str(temp_path / "settings")
        env["PYTHONPATH"] = os.pathsep.join(
            filter(None, [str(SRC_PATH), env.get("PYTHONPATH")])
        )
        print(f"Starting MNE-Nodes with fresh settings in {temp_path / 'settings'}")
        try:
            result = subprocess.run(
                [sys.executable, "-P", "-m", "mne_nodes", *sys.argv[1:]],
                env=env,
                check=False,
            )
            return_code = result.returncode
        except KeyboardInterrupt:
            return_code = 130
        finally:
            for path in HOME_STATE:
                _remove(path)
                if path in backups:
                    _copy(backups[path], path)
            print("Previous MNE-Nodes state restored.")
    return return_code


if __name__ == "__main__":
    sys.exit(main())
