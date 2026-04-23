"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import sys

from PySide6.QtWidgets import QApplication
from mne_nodes.gui.function_widgets import FunctionImporter
from mne_nodes.pipeline.streams import init_logging

init_logging()
app = QApplication(sys.argv)
file_path = r"C:\Users\martin\Code\mne-nodes\mne_nodes\core_functions\core_functions.py"
fi = FunctionImporter(code=file_path, allow_exec=True)
fi.show()
sys.exit(app.exec())
