"""Dataset-wide, read-only auxiliary-data overview."""

from qtpy.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QPersistentModelIndex,
    QSortFilterProxyModel,
    Qt,
)
from qtpy.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QStyle,
    QTableView,
    QVBoxLayout,
)

from mne_nodes.backend.data_overview import (
    DataAvailability,
    DataOverview,
    discover_data_overview,
)
from mne_nodes.backend.exception_handling import ExceptionTuple, gui_error
from mne_nodes.gui.dialogs import ErrorDialog
from mne_nodes.gui.run_widgets import WorkerDialog

_ROOT_INDEX = QModelIndex()


class DataOverviewModel(QAbstractTableModel):
    """Expose a scan snapshot without allocating per-cell items or doing I/O."""

    columns = (
        "Recording",
        "Anatomy candidates",
        "FreeSurfer subject",
        "Transform",
        "Empty-room",
    )

    def __init__(self, parent: QTableView) -> None:
        super().__init__(parent)
        self._recordings: list[dict[str, str | DataAvailability]] = []
        style = parent.style()
        self.icons = {
            "present": style.standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton),
            "missing": style.standardIcon(QStyle.StandardPixmap.SP_DialogCancelButton),
            "error": style.standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning),
            "not_applicable": style.standardIcon(
                QStyle.StandardPixmap.SP_DialogHelpButton
            ),
        }

    def replace(self, overview: DataOverview) -> None:
        """Replace the entire snapshot with a single model reset."""
        self.beginResetModel()
        self._recordings = overview.recordings
        self.endResetModel()

    def rowCount(
        self, parent: QModelIndex | QPersistentModelIndex = _ROOT_INDEX
    ) -> int:
        """Return the number of participant recordings."""
        return 0 if parent.isValid() else len(self._recordings)

    def columnCount(
        self, parent: QModelIndex | QPersistentModelIndex = _ROOT_INDEX
    ) -> int:
        """Return the fixed number of overview columns."""
        return 0 if parent.isValid() else len(self.columns)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        """Describe the recording and availability columns."""
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                return self.columns[section]
            return section + 1
        return None

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        """Return cached names, icons and accessible status explanations."""
        if not index.isValid():
            return None
        value = self._recordings[index.row()][self.columns[index.column()]]
        if isinstance(value, str):
            if role in (
                Qt.ItemDataRole.DisplayRole,
                Qt.ItemDataRole.ToolTipRole,
                Qt.ItemDataRole.AccessibleTextRole,
                Qt.ItemDataRole.UserRole,
            ):
                return value
            return None
        if role == Qt.ItemDataRole.DecorationRole:
            return self.icons[value.state]
        if role in (Qt.ItemDataRole.ToolTipRole, Qt.ItemDataRole.AccessibleTextRole):
            return f"{value.state.replace('_', ' ').capitalize()}: {value.description}"
        if role == Qt.ItemDataRole.UserRole:
            return value.state
        if role == Qt.ItemDataRole.DisplayRole and value.state == "not_applicable":
            return "N/A"
        return None


class DataOverviewDialog(QDialog):
    """Show recording associations and all discovered auxiliary data."""

    def __init__(self, controller, parent=None) -> None:
        super().__init__(parent)
        self.ct = controller
        self._worker = None
        self.setWindowTitle("Data overview")
        self.resize(1100, 650)
        layout = QVBoxLayout(self)
        description = QLabel(
            "One row per participant recording. Anatomy indicates subject/session "
            "candidates, not a verified MRI association. FreeSurfer subjects use "
            "coregistration mappings. Presence does not verify reconstruction or "
            "alignment quality. Empty-room associations use MNE-BIDS."
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        layout.addWidget(
            QLabel(
                "Check: present | Cross: missing | Warning: lookup error | "
                "N/A: not applicable. Hover over a cell for details."
            )
        )
        self.table = QTableView()
        self.model = DataOverviewModel(self.table)
        self.proxy = QSortFilterProxyModel(self.table)
        self.proxy.setSourceModel(self.model)
        self.proxy.setSortRole(Qt.ItemDataRole.UserRole)
        self.table.setModel(self.proxy)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setDefaultSectionSize(160)
        self.table.setColumnWidth(0, 420)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        layout.addWidget(self.table, 1)
        buttons = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.update_widgets)
        buttons.addWidget(self.refresh_button)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        buttons.addWidget(close)
        layout.addLayout(buttons)

    def update_widgets(self) -> None:
        """Scan in a worker so association lookup does not block the application."""
        if self._worker is not None:
            return
        with gui_error():
            self.ct.ensure_bids_root()
            self.status.setText("Scanning dataset...")
            self.refresh_button.setEnabled(False)
            self._worker = WorkerDialog(
                self,
                discover_data_overview,
                controller=self.ct,
                return_exception=True,
                title="Data overview",
            )
            self._worker.set_pgbar_max(0)
            self._worker.label_changed("Discovering dataset...")
            self._worker.thread_finished.connect(self._discovered)

    def _discovered(self, result: DataOverview | ExceptionTuple) -> None:
        self._worker = None
        self.refresh_button.setEnabled(True)
        if isinstance(result, ExceptionTuple):
            self.model.replace(DataOverview([], {}))
            self.status.setText("Dataset scan failed.")
            ErrorDialog(result, parent=self).exec()
            return
        self.model.replace(result)
        self.status.setText(
            f"{len(result.recordings)} recordings; "
            + "Dataset totals (including unassociated data): "
            + "; ".join(
                f"{kind}: {len(paths)}" for kind, paths in result.inventory.items()
            )
        )
        self.ct.refresh_input_outputs()
