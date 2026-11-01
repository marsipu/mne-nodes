"""Try traceback copying, report redaction and the GitHub issue draft flow.

Run from the repository root with ``python -m development.error_dialog_tester``.
No data is read and no issue is submitted automatically.
"""

import sys
import traceback
from pathlib import Path

from qtpy.QtWidgets import QApplication

from mne_nodes.gui.dialogs.error_dialog import ErrorDialog


def main() -> int:
    """Display a deliberate demo error using the real reporting dialogs."""
    app = QApplication(sys.argv)
    demo_path = Path.home() / "mne-nodes-demo" / "sample_raw.fif"
    try:
        raise FileNotFoundError(
            f'Development demo: could not load "{demo_path}". '
            "This error is intentional; no file was accessed."
        )
    except FileNotFoundError as error:
        dialog = ErrorDialog(
            (type(error), error, traceback.format_exc()),
            title="Development demo error (intentional)",
        )
    dialog.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
