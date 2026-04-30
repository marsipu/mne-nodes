"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import sys
from pathlib import Path

import faulthandler

from qtpy.QtWidgets import QApplication
from mne_nodes.gui.function_widgets import FunctionImporter
from mne_nodes.pipeline.streams import init_logging

faulthandler.enable()

init_logging()
app = QApplication(sys.argv)
file_path = Path(__file__).parent.parent / "core_functions" / "core_functions.py"
fi = FunctionImporter(file_path=file_path, allow_exec=True)
sys.exit(app.exec())
