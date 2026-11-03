"""Dialog for resolving function names shared by different plugins."""

import keyword

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class FunctionConflictDialog(QDialog):
    """Choose a plugin implementation or retain both with a unique name."""

    def __init__(
        self,
        conflicts: dict[str, tuple[str, str]],
        occupied: set[str],
        parent: QWidget | None = None,
        *,
        source_renamable: set[str] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Conflicting Plugin Functions")
        self.resize(1000, 400)
        self.choices: dict[str, tuple[str, str]] | None = None
        self.occupied = occupied
        self.rows: dict[str, tuple[QComboBox, QLineEdit]] = {}
        layout = QVBoxLayout(self)
        label = QLabel(
            "These plugins provide the same node name, not necessarily identical "
            "code. Choose an implementation or rename the incoming function.\n"
            "Aliases only affect this pipeline. Source renames update local Python "
            "and JSON files, keeping the old Python name as a compatibility alias."
        )
        label.setWordWrap(True)
        layout.addWidget(label)
        self.table = QTableWidget(len(conflicts), 5)
        self.table.setHorizontalHeaderLabels(
            [
                "Function",
                "Existing plugin / source",
                "Incoming plugin / source",
                "Resolution",
                "New name",
            ]
        )
        for row, (name, origins) in enumerate(conflicts.items()):
            for column, text in enumerate((name, *origins)):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, column, item)
            action = QComboBox()
            for text, value in (
                ("Choose...", ""),
                ("Keep existing", "existing"),
                ("Use incoming", "incoming"),
                ("Keep both: node alias", "alias"),
                ("Keep both: rename Python source", "source"),
            ):
                if value == "source" and name not in (source_renamable or set()):
                    continue
                action.addItem(text, value)
            rename = QLineEdit()
            rename.setPlaceholderText("Unique function name")
            rename.setEnabled(False)
            action.currentIndexChanged.connect(
                lambda _, action=action, rename=rename: rename.setEnabled(
                    action.currentData() in ("alias", "source")
                )
            )
            self.rows[name] = (action, rename)
            self.table.setCellWidget(row, 3, action)
            self.table.setCellWidget(row, 4, rename)
        self.table.resizeColumnsToContents()
        self.table.resizeRowsToContents()
        layout.addWidget(self.table)
        self.error = QLabel()
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self) -> None:
        """Require an explicit choice and unique, valid names before accepting."""
        choices = {}
        occupied = set(self.occupied)
        for name, (action, rename) in self.rows.items():
            mode = action.currentData()
            new_name = rename.text().strip()
            if not mode:
                self.error.setText(f"Choose a resolution for {name}.")
                return
            if mode in ("alias", "source"):
                if not new_name.isidentifier() or keyword.iskeyword(new_name):
                    self.error.setText(f"Enter a valid Python identifier for {name}.")
                    return
                if new_name in occupied:
                    self.error.setText(f"The name {new_name!r} is already in use.")
                    return
                occupied.add(new_name)
            choices[name] = (mode, new_name)
        self.choices = choices
        super().accept()


def resolve_function_conflicts(
    conflicts: dict[str, tuple[str, str]],
    occupied: set[str],
    parent: QWidget | None = None,
    *,
    source_renamable: set[str] | None = None,
) -> dict[str, tuple[str, str]] | None:
    """Return explicit resolutions, or None if loading was cancelled."""
    dialog = FunctionConflictDialog(
        conflicts, occupied, parent, source_renamable=source_renamable
    )
    if dialog.exec() == QDialog.DialogCode.Accepted:
        return dialog.choices
    return None
