"""Run MNE-Nodes as if it were started for the first time.

The app uses temporary settings, home and data directories, including an empty
sample-data cache, like a fresh container. Your original settings, log and home
files are never touched. Temporary state is removed after the app closes.
Files explicitly selected outside the temporary directory are not restored.
Additional command-line arguments are passed on to MNE-Nodes.

Close any existing MNE-Nodes instances before running this script:
    conda run -n mnedev python development/clean_start.py
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

SRC_PATH = Path(__file__).resolve().parents[1] / "src"


def main() -> int:
    """Run MNE-Nodes with disposable state without changing the original state."""
    with tempfile.TemporaryDirectory(prefix="mne-nodes-fresh-") as temp_dir:
        temp_path = Path(temp_dir)
        env = os.environ.copy()
        home = temp_path / "home"
        home.mkdir()
        env["HOME"] = str(home)
        env["USERPROFILE"] = str(home)
        for variable, directory in (
            ("APPDATA", home / "AppData" / "Roaming"),
            ("LOCALAPPDATA", home / "AppData" / "Local"),
            ("XDG_CONFIG_HOME", home / ".config"),
            ("MNE_DATA", home / "mne_data"),
        ):
            directory.mkdir(parents=True)
            env[variable] = str(directory)
        env["MNENODES_SETTINGS_DIR"] = str(temp_path / "settings")
        env["PYTHONPATH"] = os.pathsep.join(
            filter(None, [str(SRC_PATH), env.get("PYTHONPATH")])
        )
        print(f"Starting MNE-Nodes with temporary state in {temp_path}", flush=True)
        try:
            with subprocess.Popen(
                [sys.executable, "-P", "-m", "mne_nodes", *sys.argv[1:]],
                env=env,
                cwd=temp_path,
            ) as process:
                try:
                    return_code = process.wait()
                except KeyboardInterrupt:
                    # Do not remove temporary state while the child is still using it.
                    if process.poll() is None:
                        process.terminate()
                    process.wait()
                    return_code = 130
        except KeyboardInterrupt:
            return_code = 130
        finally:
            print("MNE-Nodes closed; original state was left unchanged.", flush=True)
    return return_code


if __name__ == "__main__":
    sys.exit(main())
