"""Qt6 / Qt5 enum compatibility helpers shared across the project.

This module centralizes the enum indirections that changed between Qt5 and Qt6
so that individual widgets / pipeline components can rely on a single import.

The constants here DO NOT require a QApplication instance and are therefore
safe to import early (e.g. during Controller initialization in headless mode).
A lazy helper ``_lazy_font_options`` is provided to avoid querying font
families before a QApplication exists, which can cause crashes on some
platforms.
"""

from __future__ import annotations

from qtpy.QtCore import Qt
from qtpy.QtGui import QFontDatabase, QPainter
from qtpy.QtWidgets import (
    QComboBox,
    QMessageBox,
    QSizePolicy,
    QMainWindow,
    QGraphicsView,
)

# -----------------------------------------------------------------------------
# QSizePolicy changes in Qt6
# -----------------------------------------------------------------------------
try:  # Qt6 style
    SP_MAX = QSizePolicy.Policy.Maximum
    SP_EXP = QSizePolicy.Policy.Expanding
    SP_PREF = QSizePolicy.Policy.Preferred
    SP_MIN_EXP = QSizePolicy.Policy.MinimumExpanding
except AttributeError:  # Qt5 fallback
    SP_MAX = QSizePolicy.Maximum  # type: ignore[attr-defined]
    SP_EXP = QSizePolicy.Expanding  # type: ignore[attr-defined]
    SP_PREF = QSizePolicy.Preferred  # type: ignore[attr-defined]
    SP_MIN_EXP = QSizePolicy.MinimumExpanding  # type: ignore[attr-defined]

# Additional QSizePolicy convenience
try:
    SP_FIXED = QSizePolicy.Policy.Fixed
except AttributeError:  # Qt5
    SP_FIXED = QSizePolicy.Fixed  # type: ignore[attr-defined]

# -----------------------------------------------------------------------------
# QComboBox size adjust policy enum move
# -----------------------------------------------------------------------------
try:
    CMBX_ADJUST_CONTENTS = QComboBox.SizeAdjustPolicy.AdjustToContents
except AttributeError:
    CMBX_ADJUST_CONTENTS = QComboBox.AdjustToContents  # type: ignore[attr-defined]

# -----------------------------------------------------------------------------
# QMessageBox standard buttons (Qt6 move)
# -----------------------------------------------------------------------------
try:
    MB_YES = QMessageBox.StandardButton.Yes
    MB_NO = QMessageBox.StandardButton.No
    MB_CANCEL = QMessageBox.StandardButton.Cancel
    MB_OK = QMessageBox.StandardButton.Ok
    MB_NOBUTTON = QMessageBox.StandardButton.NoButton
except AttributeError:
    MB_YES = QMessageBox.Yes  # type: ignore[attr-defined]
    MB_NO = QMessageBox.No  # type: ignore[attr-defined]
    MB_CANCEL = QMessageBox.Cancel  # type: ignore[attr-defined]
    MB_OK = QMessageBox.Ok  # type: ignore[attr-defined]
    MB_NOBUTTON = QMessageBox.NoButton  # type: ignore[attr-defined]

# -----------------------------------------------------------------------------
# QFontDatabase writing system enum move
# -----------------------------------------------------------------------------
try:
    LATIN_WRITING_SYSTEM = QFontDatabase.WritingSystem.Latin
except AttributeError:
    LATIN_WRITING_SYSTEM = QFontDatabase.Latin  # type: ignore[attr-defined]

# -----------------------------------------------------------------------------
# Additional alignment / orientation / dock / state enums
# -----------------------------------------------------------------------------
try:
    ALIGN_CENTER = Qt.AlignmentFlag.AlignCenter
    ALIGN_RIGHT = Qt.AlignmentFlag.AlignRight
    ALIGN_LEFT = Qt.AlignmentFlag.AlignLeft
    ALIGN_TOP = Qt.AlignmentFlag.AlignTop
    ALIGN_HCENTER = Qt.AlignmentFlag.AlignHCenter
    ALIGN_VCENTER = Qt.AlignmentFlag.AlignVCenter
    HORIZONTAL = Qt.Orientation.Horizontal
    VERTICAL = Qt.Orientation.Vertical
    RIGHT_DOCK = Qt.DockWidgetArea.RightDockWidgetArea
    LEFT_DOCK = Qt.DockWidgetArea.LeftDockWidgetArea
    BOTTOM_DOCK = Qt.DockWidgetArea.BottomDockWidgetArea
    TOP_DOCK = Qt.DockWidgetArea.TopDockWidgetArea
    CHECKED = Qt.CheckState.Checked
except AttributeError:
    ALIGN_CENTER = Qt.AlignCenter  # type: ignore[attr-defined]
    ALIGN_RIGHT = Qt.AlignRight  # type: ignore[attr-defined]
    ALIGN_LEFT = Qt.AlignLeft  # type: ignore[attr-defined]
    ALIGN_TOP = Qt.AlignTop  # type: ignore[attr-defined]
    ALIGN_HCENTER = Qt.AlignHCenter  # type: ignore[attr-defined]
    ALIGN_VCENTER = Qt.AlignVCenter  # type: ignore[attr-defined]
    HORIZONTAL = Qt.Horizontal  # type: ignore[attr-defined]
    VERTICAL = Qt.Vertical  # type: ignore[attr-defined]
    RIGHT_DOCK = Qt.RightDockWidgetArea  # type: ignore[attr-defined]
    LEFT_DOCK = Qt.LeftDockWidgetArea  # type: ignore[attr-defined]
    BOTTOM_DOCK = Qt.BottomDockWidgetArea  # type: ignore[attr-defined]
    TOP_DOCK = Qt.TopDockWidgetArea  # type: ignore[attr-defined]
    CHECKED = Qt.Checked  # type: ignore[attr-defined]

# -----------------------------------------------------------------------------
# Additional enum helpers
# -----------------------------------------------------------------------------
try:
    ELIDE_RIGHT = Qt.TextElideMode.ElideRight
except AttributeError:  # Qt5
    ELIDE_RIGHT = Qt.ElideRight  # type: ignore[attr-defined]

try:
    KEEP_ASPECT_RATIO = Qt.AspectRatioMode.KeepAspectRatio
except AttributeError:
    KEEP_ASPECT_RATIO = Qt.KeepAspectRatio  # type: ignore[attr-defined]

try:
    SMOOTH_TRANSFORMATION = Qt.TransformationMode.SmoothTransformation
except AttributeError:
    SMOOTH_TRANSFORMATION = Qt.SmoothTransformation  # type: ignore[attr-defined]

try:
    UNCHECKED = Qt.CheckState.Unchecked
except AttributeError:
    UNCHECKED = Qt.Unchecked  # type: ignore[attr-defined]

try:
    NO_TEXT_INTERACTION = Qt.TextInteractionFlag.NoTextInteraction
except AttributeError:
    NO_TEXT_INTERACTION = Qt.NoTextInteraction  # type: ignore[attr-defined]

# -----------------------------------------------------------------------------
# Item flag and focus policy compatibility
# -----------------------------------------------------------------------------
try:
    ITEM_IS_USER_CHECKABLE = Qt.ItemFlag.ItemIsUserCheckable
    ITEM_IS_EDITABLE = Qt.ItemFlag.ItemIsEditable
    ITEM_IS_ENABLED = Qt.ItemFlag.ItemIsEnabled
    ITEM_IS_SELECTABLE = Qt.ItemFlag.ItemIsSelectable
    NO_ITEM_FLAGS = Qt.ItemFlag.NoItemFlags
except AttributeError:  # Qt5
    ITEM_IS_USER_CHECKABLE = Qt.ItemIsUserCheckable  # type: ignore[attr-defined]
    ITEM_IS_EDITABLE = Qt.ItemIsEditable  # type: ignore[attr-defined]
    ITEM_IS_ENABLED = Qt.ItemIsEnabled  # type: ignore[attr-defined]
    ITEM_IS_SELECTABLE = Qt.ItemIsSelectable  # type: ignore[attr-defined]
    NO_ITEM_FLAGS = Qt.NoItemFlags  # type: ignore[attr-defined]

try:
    STRONG_FOCUS = Qt.FocusPolicy.StrongFocus
    WHEEL_FOCUS = Qt.FocusPolicy.WheelFocus
except AttributeError:
    STRONG_FOCUS = Qt.StrongFocus  # type: ignore[attr-defined]
    WHEEL_FOCUS = Qt.WheelFocus  # type: ignore[attr-defined]

try:
    DISPLAY_ROLE = Qt.ItemDataRole.DisplayRole
    EDIT_ROLE = Qt.ItemDataRole.EditRole
    CHECK_STATE_ROLE = Qt.ItemDataRole.CheckStateRole
    FOREGROUND_ROLE = Qt.ItemDataRole.ForegroundRole
    BACKGROUND_ROLE = Qt.ItemDataRole.BackgroundRole
    TOOLTIP_ROLE = Qt.ItemDataRole.ToolTipRole
    FONT_ROLE = Qt.ItemDataRole.FontRole
except AttributeError:
    DISPLAY_ROLE = Qt.DisplayRole  # type: ignore[attr-defined]
    EDIT_ROLE = Qt.EditRole  # type: ignore[attr-defined]
    CHECK_STATE_ROLE = Qt.CheckStateRole  # type: ignore[attr-defined]
    FOREGROUND_ROLE = Qt.ForegroundRole  # type: ignore[attr-defined]
    BACKGROUND_ROLE = Qt.BackgroundRole  # type: ignore[attr-defined]
    TOOLTIP_ROLE = Qt.ToolTipRole  # type: ignore[attr-defined]
    FONT_ROLE = Qt.FontRole  # type: ignore[attr-defined]

# -----------------------------------------------------------------------------
# Key and mouse button enums
# -----------------------------------------------------------------------------
try:  # Key enums
    KEY_C = Qt.Key.Key_C
    KEY_DELETE = Qt.Key.Key_Delete
    KEY_UP = Qt.Key.Key_Up
    KEY_RETURN = Qt.Key.Key_Return
except AttributeError:
    KEY_C = Qt.Key_C  # type: ignore[attr-defined]
    KEY_DELETE = Qt.Key_Delete  # type: ignore[attr-defined]
    KEY_UP = Qt.Key_Up  # type: ignore[attr-defined]
    KEY_RETURN = Qt.Key_Return  # type: ignore[attr-defined]

try:
    KEY_NO_MODIFIER = Qt.KeyboardModifier.NoModifier
    KEY_SHIFT_MODIFIER = Qt.KeyboardModifier.ShiftModifier
except AttributeError:
    KEY_NO_MODIFIER = Qt.NoModifier  # type: ignore[attr-defined]
    KEY_SHIFT_MODIFIER = Qt.ShiftModifier  # type: ignore[attr-defined]

try:  # Modifier enums
    MOD_ALT = Qt.KeyboardModifier.AltModifier
    MOD_SHIFT = Qt.KeyboardModifier.ShiftModifier
    NO_MODIFIER = Qt.KeyboardModifier.NoModifier
except AttributeError:
    MOD_ALT = Qt.AltModifier  # type: ignore[attr-defined]
    MOD_SHIFT = Qt.ShiftModifier  # type: ignore[attr-defined]
    NO_MODIFIER = Qt.NoModifier  # type: ignore[attr-defined]

try:  # Mouse buttons
    MOUSE_LEFT = Qt.MouseButton.LeftButton
    MOUSE_RIGHT = Qt.MouseButton.RightButton
    MOUSE_MIDDLE = Qt.MouseButton.MiddleButton
    MOUSE_NONE = Qt.MouseButton.NoButton
except AttributeError:
    MOUSE_LEFT = Qt.LeftButton  # type: ignore[attr-defined]
    MOUSE_RIGHT = Qt.RightButton  # type: ignore[attr-defined]
    MOUSE_MIDDLE = Qt.MidButton  # type: ignore[attr-defined]
    MOUSE_NONE = Qt.NoButton  # type: ignore[attr-defined]

try:  # Drop actions
    DROP_COPY = Qt.DropAction.CopyAction
except AttributeError:
    DROP_COPY = Qt.CopyAction  # type: ignore[attr-defined]

try:  # Item selection mode
    SELECTION_INTERSECTS = Qt.ItemSelectionMode.IntersectsItemShape
except AttributeError:
    SELECTION_INTERSECTS = Qt.IntersectsItemShape  # type: ignore[attr-defined]

try:  # Scrollbar policy
    SCROLLBAR_OFF = Qt.ScrollBarPolicy.ScrollBarAlwaysOff
except AttributeError:
    SCROLLBAR_OFF = Qt.ScrollBarAlwaysOff  # type: ignore[attr-defined]

try:  # QMainWindow dock options
    DOCK_ANIMATED = QMainWindow.DockOption.AnimatedDocks
except AttributeError:
    DOCK_ANIMATED = QMainWindow.AnimatedDocks  # type: ignore[attr-defined]

try:  # QGraphicsView viewport update
    VIEWPORT_FULL_UPDATE = QGraphicsView.ViewportUpdateMode.FullViewportUpdate
except AttributeError:
    VIEWPORT_FULL_UPDATE = QGraphicsView.FullViewportUpdate  # type: ignore[attr-defined]

try:  # QGraphicsView cache mode
    CACHE_BACKGROUND = QGraphicsView.CacheModeFlag.CacheBackground
except AttributeError:
    CACHE_BACKGROUND = QGraphicsView.CacheBackground  # type: ignore[attr-defined]

try:  # QGraphicsView optimization flag
    OPT_NO_ANTIALIAS_ADJUST = QGraphicsView.OptimizationFlag.DontAdjustForAntialiasing
except AttributeError:
    OPT_NO_ANTIALIAS_ADJUST = QGraphicsView.DontAdjustForAntialiasing  # type: ignore[attr-defined]

# -----------------------------------------------------------------------------
# QPainter render hint (antialiasing)
# -----------------------------------------------------------------------------
try:  # Qt6
    RENDER_ANTIALIAS = QPainter.RenderHint.Antialiasing
except AttributeError:  # Qt5
    try:
        RENDER_ANTIALIAS = QPainter.Antialiasing  # type: ignore[attr-defined]
    except AttributeError:  # pragma: no cover
        RENDER_ANTIALIAS = 0

# -----------------------------------------------------------------------------
# Pen / Brush / Join / Cap style enums (centralized for graphics usage)
# -----------------------------------------------------------------------------
try:  # Qt6 enum namespaces
    PEN_SOLID = Qt.PenStyle.SolidLine
    PEN_DASH = Qt.PenStyle.DashLine
    PEN_DOT = Qt.PenStyle.DotLine
    PEN_DASH_DOT = Qt.PenStyle.DashDotLine
    PEN_NONE = Qt.PenStyle.NoPen
    PEN_JOIN_MITER = Qt.PenJoinStyle.MiterJoin
    PEN_CAP_ROUND = Qt.PenCapStyle.RoundCap
    NO_BRUSH = Qt.BrushStyle.NoBrush
except AttributeError:  # Qt5 fallback attributes
    PEN_SOLID = Qt.SolidLine  # type: ignore[attr-defined]
    PEN_DASH = Qt.DashLine  # type: ignore[attr-defined]
    PEN_DOT = Qt.DotLine  # type: ignore[attr-defined]
    PEN_DASH_DOT = Qt.DashDotLine  # type: ignore[attr-defined]
    PEN_NONE = Qt.NoPen  # type: ignore[attr-defined]
    PEN_JOIN_MITER = Qt.MiterJoin  # type: ignore[attr-defined]
    PEN_CAP_ROUND = Qt.RoundCap  # type: ignore[attr-defined]
    NO_BRUSH = Qt.NoBrush  # type: ignore[attr-defined]

# -----------------------------------------------------------------------------
# QApplication attributes
# -----------------------------------------------------------------------------
try:
    AA_DONT_USE_NATIVE_DIALOGS = Qt.ApplicationAttribute.AA_DontUseNativeDialogs
    WA_DELETE_ON_CLOSE = Qt.WidgetAttribute.WA_DeleteOnClose
except AttributeError:
    AA_DONT_USE_NATIVE_DIALOGS = Qt.AA_DontUseNativeDialogs  # type: ignore[attr-defined]
    WA_DELETE_ON_CLOSE = Qt.WA_DeleteOnClose  # type: ignore[attr-defined]

# --------------------------------------------------------------------------------
# Global colors
# --------------------------------------------------------------------------------
try:
    WHITE = Qt.GlobalColor.white
    BLACK = Qt.GlobalColor.black
    RED = Qt.GlobalColor.red
    GREEN = Qt.GlobalColor.green
    DARK_GREEN = Qt.GlobalColor.darkGreen
    BLUE = Qt.GlobalColor.blue
    YELLOW = Qt.GlobalColor.yellow
    GRAY = Qt.GlobalColor.gray
    LIGHT_GRAY = Qt.GlobalColor.lightGray
    DARK_GRAY = Qt.GlobalColor.darkGray
    TRANSPARENT = Qt.GlobalColor.transparent
except AttributeError:
    WHITE = Qt.white  # type: ignore[attr-defined]
    BLACK = Qt.black  # type: ignore[attr-defined]
    RED = Qt.red  # type: ignore[attr-defined]
    GREEN = Qt.green  # type: ignore[attr-defined]
    DARK_GREEN = Qt.darkGreen  # type: ignore[attr-defined]
    BLUE = Qt.blue  # type: ignore[attr-defined]
    YELLOW = Qt.yellow  # type: ignore[attr-defined]
    GRAY = Qt.gray  # type: ignore[attr-defined]
    LIGHT_GRAY = Qt.lightGray  # type: ignore[attr-defined]
    DARK_GRAY = Qt.darkGray  # type: ignore[attr-defined]
    TRANSPARENT = Qt.transparent  # type: ignore[attr-defined]

# -----------------------------------------------------------------------------
# Lazy font enumeration helper (avoid crashing before QApplication exists)
# -----------------------------------------------------------------------------


def _lazy_font_options():
    """Return available font families, falling back to a small default list.

    On some platforms querying QFontDatabase before a Q(Gui)Application
    exists can cause issues. We guard against that here.
    """
    defaults = ["Sans Serif", "Serif", "Monospace"]
    try:
        from qtpy.QtGui import QGuiApplication

        if QGuiApplication.instance() is None:
            return defaults
        families = list(QFontDatabase.families(LATIN_WRITING_SYSTEM))
        if not families:
            return defaults
        return families
    except (ImportError, RuntimeError):
        # ImportError if qtpy backend missing; RuntimeError in some headless cases
        return defaults
