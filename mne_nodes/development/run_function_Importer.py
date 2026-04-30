"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import sys
from pathlib import Path

import faulthandler

from qtpy.QtWidgets import QApplication
from mne_nodes.pipeline.streams import init_logging


def main() -> None:
    faulthandler.enable()
    init_logging()

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    # Import GUI-heavy modules only after QApplication exists.
    from mne_nodes.gui.function_widgets import FunctionImporter

    file_path = Path(__file__).parent.parent / "core_functions" / "core_functions.py"
    FunctionImporter(file_path=file_path, allow_exec=True).open()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
