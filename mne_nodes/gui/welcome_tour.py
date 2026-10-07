import shutil
import sys
from collections.abc import Callable
from copy import deepcopy
from html import escape
from importlib import import_module
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, NotRequired, TypedDict

from qtpy.QtCore import QEvent, QObject, QPoint, QRect, QSize, Qt, QTimer, Signal
from qtpy.QtGui import (
    QColor,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPalette,
    QPixmap,
)
from qtpy.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QAbstractScrollArea,
    QAbstractSlider,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QDockWidget,
    QGraphicsDropShadowEffect,
    QGraphicsItem,
    QGraphicsProxyWidget,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMenuBar,
    QPushButton,
    QTabBar,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from mne_nodes.gui.gui_theme import WELCOME_TOUR_STYLE
from mne_nodes.gui.gui_utils import ask_user
from mne_nodes.gui.run_widgets import WorkerDialog
from mne_nodes.pipeline.data_import import load_sample_bids
from mne_nodes.pipeline.exception_handling import ExceptionTuple

if TYPE_CHECKING:
    from mne_nodes.gui.main_window import MainWindow
    from mne_nodes.pipeline.controller import Controller

WELCOME_TOUR_PADDING = 10
WELCOME_CONFIG_PATH = Path(__file__).parents[1] / "extra" / "Welcome_pipeline.json"
WELCOME_CROP_CODE = (
    "def crop_raw(raw, tmin=0.0, tmax=10.0):\n"
    '    """Crop a copy; times are in seconds."""\n'
    "    raw = raw.copy()\n"
    "    raw.crop(tmin=tmin, tmax=tmax)\n"
    "    return raw\n"
)


class WelcomeTourStep(TypedDict):
    """A tour target and optional task, resolved from current application state."""

    widget: QWidget | QGraphicsItem | Callable[[], QWidget | QGraphicsItem | None]
    text: str
    action: NotRequired[Callable[[], None]]
    action_text: NotRequired[str]
    cleanup: NotRequired[Callable[[], None]]
    is_complete: NotRequired[Callable[[], bool]]
    requires_completion: NotRequired[bool]
    interactive_widgets: NotRequired[list[QWidget] | Callable[[], list[QWidget]]]
    interactive_views: NotRequired[list[QGraphicsView]]
    interactive_items: NotRequired[
        list[QGraphicsItem] | Callable[[], list[QGraphicsItem]]
    ]


class WelcomeTourOverlay(QWidget):
    """
    Semi-transparent overlay that covers the entire app window.
    It can highlight specific rectangular areas by cutting 'holes' into the overlay.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self.highlight_path: QPainterPath | None = None
        self.dim_color = QColor(0, 0, 0, 160)
        self._cache: QPixmap | None = None

    def set_highlight(self, path: QPainterPath):
        self.highlight_path = path
        self._cache = None
        self.update()

    def resizeEvent(self, event):
        self._cache = None
        super().resizeEvent(event)

    def _render_cache(self) -> QPixmap:
        ratio = self.devicePixelRatioF()
        pixmap = QPixmap(self.size() * ratio)
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        dim_path = QPainterPath()
        dim_path.setFillRule(Qt.FillRule.OddEvenFill)
        dim_path.addRect(self.rect())
        dim_path.addPath(self.highlight_path)
        painter.fillPath(dim_path, self.dim_color)
        painter.end()
        return pixmap

    def paintEvent(self, event):
        if not self.highlight_path:
            return
        # Repaints of widgets below the overlay also repaint it, so only blit here.
        if self._cache is None:
            self._cache = self._render_cache()
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._cache)


class WelcomeTourWidget(QWidget):
    """
    Floating widget that displays text for each step.
    """

    next_clicked = Signal()
    prev_clicked = Signal()
    cancel_clicked = Signal()
    action_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("WelcomeTourWidget")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)

        self.label = QLabel("Welcome step text")
        self.label.setObjectName("tourLabel")
        self.label.setWordWrap(True)
        self.label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.hide()

        self.next_btn = QPushButton("Next")
        self.next_btn.setObjectName("nextButton")
        self.prev_btn = QPushButton("Back")
        self.prev_btn.setObjectName("backButton")
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("cancelButton")
        self.action_btn = QPushButton()
        self.action_btn.hide()
        self.action_btn.clicked.connect(self.action_clicked)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        btns.addWidget(self.cancel_btn)
        btns.addWidget(self.prev_btn)
        btns.addWidget(self.next_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(12)
        layout.addWidget(self.label)
        layout.addWidget(self.status_label)
        layout.addWidget(self.action_btn)
        layout.addLayout(btns)
        self._button_layout = btns
        self._content_layout = layout

        self.prev_btn.clicked.connect(self.prev_clicked)
        self.next_btn.clicked.connect(self.next_clicked)
        self.cancel_btn.clicked.connect(self.cancel_clicked)

        self.resize(300, 150)
        self.setStyleSheet(WELCOME_TOUR_STYLE)
        self._apply_theme()

    def _apply_theme(self):
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 5)
        shadow_color = self.palette().color(QPalette.ColorRole.Highlight)
        shadow_color.setAlpha(110)
        shadow.setColor(shadow_color)
        self.setGraphicsEffect(shadow)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange:
            self._apply_theme()

    def set_text(self, text: str):
        self.label.setText(text)

    def set_status(self, text: str) -> None:
        """Display task feedback, or hide it for an informational step."""
        self.status_label.setText(text)
        self.status_label.setVisible(bool(text))

    def size_for_width(self, width: int) -> QSize:
        """Return the panel size required to display its current text."""
        margins = self._content_layout.contentsMargins()
        label_width = max(width - margins.left() - margins.right(), 1)
        label_height = self.label.heightForWidth(label_width)
        button_height = self._button_layout.sizeHint().height()
        height = (
            margins.top()
            + label_height
            + self._content_layout.spacing()
            + button_height
            + margins.bottom()
        )
        if not self.status_label.isHidden():
            height += (
                self.status_label.heightForWidth(label_width)
                + self._content_layout.spacing()
            )
        if not self.action_btn.isHidden():
            height += (
                self.action_btn.sizeHint().height() + self._content_layout.spacing()
            )
        return QSize(width, height)


class WelcomeTour(QObject):
    """
    Controls the tour: steps, overlay, widget positioning, transitions.
    Parameters
    ----------
    main_window : QMainWindow
        The main application window.
    steps : list of WelcomeTourStep
        Each step contains ``widget`` and ``text``. ``widget`` may be a zero-argument
        callable returning the current target, or None until it exists.

    Notes
    -----
    Steps contain ``"widget"`` and ``"text"``. Highlights use the standard
    :data:`WELCOME_TOUR_PADDING` value and the target's own shape.
    The ``finished`` signal is emitted after the tour stops observing its target,
    allowing the controller to safely replace the demo pipeline.
    Dynamic targets and optional ``is_complete`` predicates are rechecked every
    100 ms. Predicates should be cheap, side-effect-free state queries. Returning
    False displays task feedback and blocks Next; returning True enables Next
    and emits ``task_completed(index)`` before automatically advancing on the
    next event-loop turn. If the state is undone before advancing, Next is
    disabled again. Informational steps advance manually. For signal-driven tasks, use
    ``requires_completion=True`` and call ``complete_task(index)`` instead.
    Steps already passed remain available through Back and advance manually with
    Next, without rechecking completion or undoing the user's changes. They can
    also be skipped when their dynamic target no longer exists.
    Interactive widgets are disabled except for those explicitly listed in
    ``interactive_widgets`` for the active step. Descendant controls and menu
    actions belonging to those widgets remain available.
    An optional ``action`` and ``action_text`` expose a step-specific button.
    Step ``cleanup`` callbacks run on completion or cancellation before the
    demo plugins and temporary directory are removed.
    """

    finished = Signal()
    task_completed = Signal(int)

    def __init__(self, main_window, steps: list[WelcomeTourStep]):
        super().__init__()
        self.main_window = main_window
        self.steps = steps
        self.index = 0
        self._observed_objects = []
        self._observed_scrollbars = []
        self._scene = None
        self._finished = False
        self._refreshing = False
        self._target: QWidget | QGraphicsItem | None = None
        self._task_complete = False
        self._completed_tasks: set[int] = set()
        self._passed_steps: set[int] = set()
        self._widget_enabled: dict[QWidget, bool] = {}
        self._interaction_policy_dirty = True
        self._active_graphics_view: QGraphicsView | None = None
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(100)
        self._refresh_timer.timeout.connect(self.refresh)
        self._pending_refresh = QTimer(self)
        self._pending_refresh.setSingleShot(True)
        self._pending_refresh.setInterval(0)
        self._pending_refresh.timeout.connect(self.refresh)
        self._pending_advance = QTimer(self)
        self._pending_advance.setSingleShot(True)
        self._pending_advance.setInterval(0)
        self._pending_advance.timeout.connect(self.next_step)
        self._geometry_cache: tuple | None = None
        self.demo_directory: TemporaryDirectory | None = None
        self._cleanup_demo_plugin: Callable[[], None] | None = None
        self._disconnect_process_started: Callable[[], None] | None = None

        self.overlay = WelcomeTourOverlay(main_window)
        self.overlay.resize(main_window.size())
        self.overlay.show()
        self.overlay.raise_()

        self.widget = WelcomeTourWidget(main_window)
        self.widget.next_clicked.connect(self.next_step)
        self.widget.prev_clicked.connect(self.prev_step)
        self.widget.cancel_clicked.connect(self.finish)
        self.widget.action_clicked.connect(self._run_step_action)

        application = QApplication.instance()
        if application is not None:
            application.installEventFilter(self)

        self.show_step(0)

    def _make_highlight_path(self, target):
        if isinstance(target, QGraphicsItem):
            view = self._graphics_view(target)
            path = target.mapToScene(target.shape())
            path = view.mapFromScene(path)
            offset = view.viewport().mapTo(self.main_window, QPoint(0, 0))
            path.translate(offset.x(), offset.y())
        else:
            path = QPainterPath()
            path.addRect(target.rect())
            offset = target.mapTo(self.main_window, QPoint(0, 0))
            path.translate(offset.x(), offset.y())

        return path

    @staticmethod
    def _graphics_view(target):
        scene = target.scene()
        views = scene.views() if scene is not None else []
        if not views:
            raise ValueError(
                "A QGraphicsItem supplied to WelcomeTour must belong to a "
                "scene with a QGraphicsView."
            )
        return views[0]

    def compute_highlight_path(self, target):
        path = self._make_highlight_path(target)
        stroker = QPainterPathStroker()
        stroker.setWidth(WELCOME_TOUR_PADDING * 2)
        path = path.united(stroker.createStroke(path))
        return path

    def compute_highlight_rect(self, widget):
        """Return the bounding rectangle for a target's default highlight."""
        bounds = self.compute_highlight_path(widget).boundingRect()
        left = int(bounds.left() + 0.5)
        top = int(bounds.top() + 0.5)
        right = int(bounds.right() + 0.5)
        bottom = int(bounds.bottom() + 0.5)
        return QRect(left, top, right - left + 1, bottom - top + 1)

    def _clear_observers(self):
        for observed in self._observed_objects:
            observed.removeEventFilter(self)
        self._observed_objects.clear()
        for scrollbar in self._observed_scrollbars:
            scrollbar.valueChanged.disconnect(self.schedule_refresh)
        self._observed_scrollbars.clear()
        if self._scene is not None:
            self._scene.changed.disconnect(self.schedule_refresh)
            self._scene = None

    def _observe_target(self, target):
        self._clear_observers()
        objects = [self.main_window]
        if isinstance(target, QGraphicsItem):
            view = self._graphics_view(target)
            scene = target.scene()
            objects.extend([view, view.viewport()])
            for scrollbar in (view.horizontalScrollBar(), view.verticalScrollBar()):
                scrollbar.valueChanged.connect(self.schedule_refresh)
                self._observed_scrollbars.append(scrollbar)
            self._scene = scene
            scene.changed.connect(self.schedule_refresh)
        else:
            if target is not None:
                objects.append(target)
        for observed in objects:
            observed.installEventFilter(self)
            self._observed_objects.append(observed)

    @staticmethod
    def _placement_regions(bounds: QRect, target: QRect, gap: int):
        regions = []
        below_top = target.bottom() + gap
        if below_top <= bounds.bottom():
            regions.append(
                (
                    "below",
                    QRect(
                        bounds.left(),
                        below_top,
                        bounds.width(),
                        bounds.bottom() - below_top + 1,
                    ),
                )
            )
        above_bottom = target.top() - gap
        if above_bottom >= bounds.top():
            regions.append(
                (
                    "above",
                    QRect(
                        bounds.left(),
                        bounds.top(),
                        bounds.width(),
                        above_bottom - bounds.top() + 1,
                    ),
                )
            )
        right_left = target.right() + gap
        if right_left <= bounds.right():
            regions.append(
                (
                    "right",
                    QRect(
                        right_left,
                        bounds.top(),
                        bounds.right() - right_left + 1,
                        bounds.height(),
                    ),
                )
            )
        left_right = target.left() - gap
        if left_right >= bounds.left():
            regions.append(
                (
                    "left",
                    QRect(
                        bounds.left(),
                        bounds.top(),
                        left_right - bounds.left() + 1,
                        bounds.height(),
                    ),
                )
            )
        return regions

    def _move_widget_into_window(self, path):
        bounds = self.main_window.rect().adjusted(8, 8, -8, -8)
        target = path.boundingRect().toRect()
        candidates = self._placement_regions(bounds, target, gap=20)
        desired_width = max(self.widget.sizeHint().width(), 260)
        fitting = [
            (side, region)
            for side, region in candidates
            if region.width() >= desired_width
            and region.height() >= self.widget.size_for_width(desired_width).height()
        ]
        if fitting:
            # Prefer beside the target over above/below when the full panel fits.
            side, available = min(
                fitting, key=lambda candidate: candidate[0] not in ("right", "left")
            )
        elif candidates:
            side, available = max(
                candidates,
                key=lambda candidate: (
                    min(desired_width, candidate[1].width())
                    * min(
                        self.widget.size_for_width(
                            min(desired_width, candidate[1].width())
                        ).height(),
                        candidate[1].height(),
                    )
                ),
            )
        else:
            side, available = "overlap", bounds
        width = min(desired_width, available.width())
        height = min(self.widget.size_for_width(width).height(), available.height())
        self.widget.resize(width, height)
        x = target.center().x() - width // 2
        y = target.center().y() - height // 2
        if side == "right":
            x = available.left()
        elif side == "left":
            x = available.right() - width + 1
        elif side == "below":
            y = available.top()
        elif side == "above":
            y = available.bottom() - height + 1
        x = max(available.left(), min(x, available.right() - width + 1))
        y = max(available.top(), min(y, available.bottom() - height + 1))
        self.widget.move(x, y)

    def eventFilter(self, watched, event):
        if (
            event.type() == QEvent.Type.EnabledChange
            and not self._refreshing
            and not self._finished
            and watched in self._widget_enabled
        ):
            self._widget_enabled[watched] = not watched.testAttribute(
                Qt.WidgetAttribute.WA_ForceDisabled
            )
            self._interaction_policy_dirty = True
            self.schedule_refresh()
        if isinstance(watched, QMenu) and event.type() == QEvent.Type.Show:
            self._interaction_policy_dirty = True
            self.refresh()
        if event.type() == QEvent.Type.Shortcut:
            return True
        if (
            event.type() == QEvent.Type.ChildAdded
            and isinstance(watched, QWidget)
            and (watched is self.main_window or self.main_window.isAncestorOf(watched))
        ):
            self._interaction_policy_dirty = True
        if (
            self._active_graphics_view is not None
            and event.type() == QEvent.Type.MouseButtonRelease
        ):
            active_view = self._active_graphics_view
            if isinstance(watched, QWidget):
                self._active_graphics_view = None
                allowed_widgets, allowed_views = self._allowed_widgets()
                return not (
                    watched is active_view.viewport()
                    or self._interaction_allowed(
                        watched, allowed_widgets, allowed_views
                    )
                )
            # Native window input must reach Qt's widget/proxy dispatch first.
            return False
        if event.type() in (
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseButtonRelease,
            QEvent.Type.MouseMove,
            QEvent.Type.Wheel,
            QEvent.Type.ContextMenu,
        ):
            for view in self.steps[self.index].get("interactive_views", []):
                if watched is not view.viewport():
                    continue
                if event.type() == QEvent.Type.ContextMenu or (
                    event.type()
                    in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease)
                    and event.button() == Qt.MouseButton.RightButton
                ):
                    return False
                # Hover is harmless and also drives click-to-connect live pipes.
                if (
                    event.type() == QEvent.Type.MouseMove
                    and event.buttons() == Qt.MouseButton.NoButton
                ):
                    return False
                if self._active_graphics_view is view and event.type() in (
                    QEvent.Type.MouseMove,
                    QEvent.Type.MouseButtonRelease,
                ):
                    if event.type() == QEvent.Type.MouseButtonRelease:
                        self._active_graphics_view = None
                    return False
                scene_items = self.steps[self.index].get("interactive_items", [])
                if callable(scene_items):
                    scene_items = scene_items()
                if not scene_items:
                    return True
                position = (
                    event.position().toPoint()
                    if hasattr(event, "position")
                    else event.pos()
                )
                candidates = view.items(position)
                allowed = any(
                    root is candidate or root.isAncestorOf(candidate)
                    for root in scene_items
                    for candidate in candidates
                )
                if not allowed:
                    return True
                if event.type() == QEvent.Type.MouseButtonPress:
                    self._active_graphics_view = view
                return False
            if any(
                watched is view.viewport()
                for view in self.steps[self.index].get("interactive_views", [])
            ):
                return True
        if event.type() == QEvent.Type.KeyPress:
            if isinstance(watched, QWidget):
                allowed_roots, allowed_views = self._allowed_widgets()
                if self._interaction_allowed(watched, allowed_roots, allowed_views):
                    return False
            return True
        if event.type() in (
            QEvent.Type.Move,
            QEvent.Type.Resize,
            QEvent.Type.Show,
            QEvent.Type.LayoutRequest,
        ) and any(watched is observed for observed in self._observed_objects):
            self.schedule_refresh()
        return super().eventFilter(watched, event)

    def _resolve_target(self) -> QWidget | QGraphicsItem | None:
        source = self.steps[self.index]["widget"]
        target = source() if callable(source) else source
        if isinstance(target, QWidget):
            proxy = target.graphicsProxyWidget()
            if proxy is not None:
                return proxy
        return target

    @staticmethod
    def _is_interactive_widget(widget: QWidget) -> bool:
        return (
            isinstance(
                widget,
                (
                    QAbstractButton,
                    QAbstractItemView,
                    QAbstractScrollArea,
                    QAbstractSlider,
                    QAbstractSpinBox,
                    QComboBox,
                    QDockWidget,
                    QLineEdit,
                    QMenu,
                    QMenuBar,
                    QTabBar,
                    QTabWidget,
                    QToolBar,
                ),
            )
            or widget.focusPolicy() != Qt.FocusPolicy.NoFocus
        )

    @staticmethod
    def _is_within(widget: QWidget, roots: set[QWidget]) -> bool:
        return any(root is widget or root.isAncestorOf(widget) for root in roots)

    @staticmethod
    def _is_view_menu(widget: QWidget, views: set[QGraphicsView]) -> bool:
        # Qt's isAncestorOf stops at popup windows; follow menu ownership instead.
        parent = widget
        in_menu = False
        while parent is not None:
            in_menu = in_menu or isinstance(parent, QMenu)
            if parent in views:
                return in_menu
            parent = parent.parentWidget()
        return False

    def _apply_interaction_policy(self) -> None:
        """Disable controls outside this step and restore their original states."""
        self._interaction_policy_dirty = False
        step = self.steps[self.index]
        allowed = step.get("interactive_widgets", [])
        if callable(allowed):
            allowed = allowed()
        allowed_roots = set(allowed)
        allowed_roots.add(self.widget)
        allowed_views = set(step.get("interactive_views", []))

        widgets = dict.fromkeys(self.main_window.findChildren(QWidget))
        # Embedded widgets can live outside the main window's QObject tree.
        for view in self.main_window.findChildren(QGraphicsView):
            if view.scene() is None:
                continue
            for item in view.scene().items():
                if isinstance(item, QGraphicsProxyWidget):
                    root = item.widget()
                    if root is not None:
                        widgets[root] = None
                        widgets.update(dict.fromkeys(root.findChildren(QWidget)))
        interactive_widgets = [
            widget
            for widget in widgets
            if widget is not self.widget
            and not self.widget.isAncestorOf(widget)
            and self._is_interactive_widget(widget)
        ]
        for widget in interactive_widgets:
            if widget not in self._widget_enabled:
                self._widget_enabled[widget] = not widget.testAttribute(
                    Qt.WidgetAttribute.WA_ForceDisabled
                )
                widget.destroyed.connect(
                    lambda _object=None, widget=widget: self._widget_enabled.pop(
                        widget, None
                    )
                )
        for widget in interactive_widgets:
            enabled = self._interaction_allowed(widget, allowed_roots, allowed_views)
            widget.setEnabled(self._widget_enabled[widget] and enabled)

    def _allowed_widgets(self) -> tuple[set[QWidget], set[QGraphicsView]]:
        step = self.steps[self.index]
        allowed = step.get("interactive_widgets", [])
        if callable(allowed):
            allowed = allowed()
        widgets = set(allowed)
        widgets.add(self.widget)
        return widgets, set(step.get("interactive_views", []))

    def _interaction_allowed(
        self, widget: QWidget, roots: set[QWidget], views: set[QGraphicsView]
    ) -> bool:
        return (
            self._is_within(widget, roots)
            or self._is_view_menu(widget, views)
            or any(widget is view or widget is view.viewport() for view in views)
        )

    def _restore_interactions(self) -> None:
        for widget, enabled in self._widget_enabled.items():
            widget.setEnabled(enabled)
        self._widget_enabled.clear()

    def _geometry_key(self, target) -> tuple | None:
        """Return cheap values that change whenever the highlight must move."""
        window_size = self.main_window.size()
        if target is None:
            return (window_size,)
        if isinstance(target, QGraphicsItem):
            view = self._graphics_view(target)
            return (
                window_size,
                target.sceneBoundingRect(),
                view.viewportTransform(),
                view.viewport().mapTo(self.main_window, QPoint(0, 0)),
            )
        return (window_size, target.size(), target.mapTo(self.main_window, QPoint()))

    def schedule_refresh(self) -> None:
        """Coalesce bursts of scene and geometry changes into one refresh."""
        if not self._finished and not self._pending_refresh.isActive():
            self._pending_refresh.start()

    def refresh(self) -> None:
        """Resolve the target, check progress and queue completed-task advancement."""
        if self._finished or self._refreshing:
            return
        self._refreshing = True
        index = self.index
        try:
            step = self.steps[self.index]
            if self._interaction_policy_dirty:
                self._apply_interaction_policy()
            target = self._resolve_target()
            if target is not self._target:
                self._target = target
                self._observe_target(target)
            check = step.get("is_complete")
            is_task = check is not None or step.get("requires_completion", False)
            already_passed = index in self._passed_steps
            complete = already_passed or (
                bool(check())
                if check is not None
                else self.index in self._completed_tasks
            )
            can_continue = already_passed or (
                target is not None and (not is_task or complete)
            )
            if self.widget.next_btn.isEnabled() != can_continue:
                self.widget.next_btn.setEnabled(can_continue)
            if already_passed:
                status = "Step already completed. Click Next to continue."
            elif target is None:
                status = "Waiting for the target to be created."
            elif is_task:
                status = (
                    "Task completed! Moving to the next step."
                    if complete
                    else ("Complete the task to continue.")
                )
            else:
                status = ""
            status_changed = status != self.widget.status_label.text()
            if status_changed:
                self.widget.set_status(status)
            # Hover and live-pipe repaints emit scene changes at frame rate, so
            # rebuild the stroked highlight only when the target geometry moved.
            geometry_key = self._geometry_key(target)
            if geometry_key != self._geometry_cache or status_changed:
                self._geometry_cache = geometry_key
                path = (
                    self.compute_highlight_path(target)
                    if target is not None
                    else QPainterPath()
                )
                if self.overlay.size() != self.main_window.size():
                    self.overlay.resize(self.main_window.size())
                if self.overlay.highlight_path != path:
                    self.overlay.set_highlight(path)
                self._move_widget_into_window(path)
                self.widget.raise_()
            newly_complete = (
                is_task and complete and not self._task_complete and not already_passed
            )
            self._task_complete = complete
        finally:
            self._refreshing = False
        if newly_complete:
            self.task_completed.emit(index)
        if (
            not self._finished
            and self.index == index
            and is_task
            and can_continue
            and not already_passed
            and not self._pending_advance.isActive()
        ):
            self._pending_advance.start()

    def complete_task(self, index: int) -> None:
        """Record signal-driven success for a specific step, even before entry."""
        if not 0 <= index < len(self.steps):
            raise IndexError(f"Invalid welcome-tour step index: {index}")
        step = self.steps[index]
        if not step.get("requires_completion") or "is_complete" in step:
            raise ValueError("complete_task requires a signal-driven task step.")
        self._completed_tasks.add(index)
        if index == self.index:
            self.refresh()

    def show_step(self, idx):
        self._refresh_timer.stop()
        self._pending_advance.stop()
        self.index = idx
        self._interaction_policy_dirty = True
        self._geometry_cache = None
        step = self.steps[idx]
        self._target = None
        self._task_complete = False
        self._observe_target(None)
        self.widget.set_text(step["text"])
        self.widget.action_btn.setVisible("action" in step)
        self.widget.action_btn.setText(step.get("action_text", ""))
        self.widget.next_btn.setText(
            "Finished" if idx == len(self.steps) - 1 else "Next"
        )
        self.overlay.setVisible(idx != len(self.steps) - 1)
        self.widget.show()
        self.refresh()
        focus_button = (
            self.widget.next_btn
            if self.widget.next_btn.isEnabled()
            else self.widget.cancel_btn
        )
        focus_button.setFocus(Qt.FocusReason.OtherFocusReason)
        self._refresh_timer.start()

    def _run_step_action(self) -> None:
        action = self.steps[self.index].get("action")
        if action is not None:
            action()
            self.refresh()

    def next_step(self):
        if self._finished:
            return
        index = self.index
        self.refresh()
        if (
            self._finished
            or self.index != index
            or not self.widget.next_btn.isEnabled()
        ):
            return
        self._passed_steps.add(index)
        if self.index == len(self.steps) - 1:
            self.finish()
        else:
            self.show_step(self.index + 1)

    def prev_step(self):
        if self.index > 0:
            self.show_step(self.index - 1)

    def finish(self, *, notify: bool = True):
        """Close the tour and notify the controller after removing observers."""
        if self._finished:
            return
        self._finished = True
        self._refresh_timer.stop()
        self._pending_refresh.stop()
        self._pending_advance.stop()
        self._clear_observers()
        self._restore_interactions()
        application = QApplication.instance()
        if application is not None:
            application.removeEventFilter(self)
        self.overlay.hide()
        self.widget.hide()
        for step in self.steps:
            cleanup = step.get("cleanup")
            if cleanup is not None:
                cleanup()
        if self._disconnect_process_started is not None:
            self._disconnect_process_started()
            self._disconnect_process_started = None
        if self._cleanup_demo_plugin is not None:
            self._cleanup_demo_plugin()
            self._cleanup_demo_plugin = None
        if self.demo_directory is not None:
            self.demo_directory.cleanup()
            self.demo_directory = None
        self.deleteLater()
        if notify:
            self.finished.emit()


def build_welcome_steps(
    ct: "Controller", main_window: "MainWindow", *, plugin_directory: Path | None = None
) -> list[WelcomeTourStep]:
    """Return the built-in tour steps for the demo pipeline.

    Targets and allowlists are callables where the referenced object only exists
    after a user action, so they are resolved from the live viewer state.
    """
    viewer = main_window.viewer
    from mne_nodes.gui.function_widgets import FunctionImporter

    importer: FunctionImporter | None = None
    plugin_name = (
        plugin_directory.name.replace("-", "_") + "_crop"
        if plugin_directory is not None
        else "welcome_crop"
    )

    def import_crop_example() -> None:
        nonlocal importer
        if importer is not None:
            importer.show()
            importer.raise_()
            return
        if plugin_directory is None:
            raise RuntimeError("The crop example requires a temporary tour directory.")

        def load_saved_plugin(config_path: Path) -> None:
            main_window._load_saved_plugin(config_path)
            if importer is not None:
                QTimer.singleShot(0, importer.close)

        importer = FunctionImporter(
            code=WELCOME_CROP_CODE,
            parent=main_window,
            plugin_name=plugin_name,
            destination_dir=plugin_directory,
            on_saved=load_saved_plugin,
        )
        # A modal importer would block the tour's Back/Cancel/Next controls.
        importer.setWindowModality(Qt.WindowModality.NonModal)
        importer.show()

    def cleanup_crop_example() -> None:
        if importer is not None:
            importer.func_config.clear()
            importer.close()
            importer.deleteLater()
        module = sys.modules.get(plugin_name)
        if module is not None and plugin_directory is not None:
            module_file = getattr(module, "__file__", None)
            if module_file is not None and Path(module_file).parent == plugin_directory:
                sys.modules.pop(plugin_name, None)
        if plugin_directory is not None and str(plugin_directory) in sys.path:
            sys.path.remove(str(plugin_directory))

    def crop_node():
        return next(
            (
                node
                for node in viewer.function_nodes.values()
                if node.name is not None
                and ct.function_meta.get(node.name.split("-")[0], {}).get("plugin")
                == plugin_name
            ),
            None,
        )

    def crop_connection_ports() -> list[QGraphicsItem]:
        source = function_node()
        target = crop_node()
        if source is None or target is None:
            return []
        return [*source.outputs, *target.inputs]

    def crop_source_ports() -> list[QGraphicsItem]:
        source = function_node()
        return list(source.outputs) if source is not None else []

    def crop_connected() -> bool:
        source = function_node()
        target = crop_node()
        return (
            source is not None
            and target is not None
            and any(
                port.node is source
                for input_port in target.inputs
                for port in input_port.connected_ports
            )
        )

    def function_node():
        return next(iter(viewer.function_nodes.values()), None)

    def input_port():
        node = viewer.input_node
        return node.outputs[0] if node is not None and node.outputs else None

    def input_ports() -> list[QGraphicsItem]:
        port = input_port()
        return [port] if port is not None else []

    def connection_ports() -> list[QGraphicsItem]:
        source = input_port()
        node = function_node()
        if source is None or node is None:
            return []
        return [source, *node.inputs]

    def node_is_connected() -> bool:
        node = function_node()
        return node is not None and any(
            connected.node is viewer.input_node
            for port in node.inputs
            for connected in port.connected_ports
        )

    def input_widget():
        node = viewer.input_node
        return node.input_widget if node is not None else None

    def input_files_selected() -> bool:
        widget = input_widget()
        if widget is None:
            return False
        selected = ct.get("selected_inputs")
        tabs = widget.tab_widget
        return any(
            selected.get(tabs.tabText(index))
            for index in range(tabs.count())
            if tabs.tabText(index) != "Groups"
        )

    def start_button():
        node = viewer.input_node
        return node.start_button if node is not None else None

    def parameter_box():
        node = function_node()
        return node.param_box if node is not None else None

    def parameter_is_changed() -> bool:
        node = function_node()
        return node is not None and any(
            ct.parameter(name, node.name) != ct.get_default(name, node.name)
            for name in node.parameter_guis
        )

    def proxies(get_widget: Callable[[], QWidget | None]) -> list[QGraphicsItem]:
        widget = get_widget()
        proxy = widget.graphicsProxyWidget() if widget is not None else None
        return [proxy] if proxy is not None else []

    def as_list(get_widget: Callable[[], QWidget | None]) -> list[QWidget]:
        widget = get_widget()
        return [widget] if widget is not None else []

    return [
        {
            "widget": viewer,
            "text": "Welcome to mne-nodes!\nThis is the main viewer area where "
            "you can see and interact with the nodes.",
        },
        {
            "widget": lambda: viewer.input_node,
            "text": "This is the input-node. It is where you see your "
            "bids-dataset, if it is loaded. The mne-sample dataset is loaded "
            "here as an example.",
        },
        {
            "widget": input_port,
            "text": "Add a node. To add a new node, either right-click on the "
            "background or on a port of an existing node. Select example_filter "
            "from the example_plugin plugin.",
            "is_complete": lambda: function_node() is not None,
            "interactive_views": [viewer],
            "interactive_items": input_ports,
        },
        {
            "widget": function_node,
            "text": "This is a function node. Function nodes perform various "
            "operations on the data.",
        },
        {
            "widget": function_node,
            "text": "Connect the input node to your function node by dragging "
            "between compatible output and input ports.",
            "is_complete": node_is_connected,
            "interactive_views": [viewer],
            "interactive_items": connection_ports,
        },
        {
            "widget": parameter_box,
            "text": "Change a parameter of the function node, for example "
            "set lowpass to 40 instead of 30.",
            "is_complete": parameter_is_changed,
            "interactive_views": [viewer],
            "interactive_items": lambda: proxies(parameter_box),
            "interactive_widgets": lambda: as_list(parameter_box),
        },
        {
            "widget": input_widget,
            "text": "Select at least one input file by checking it in the "
            "input node before starting the pipeline.",
            "is_complete": input_files_selected,
            "interactive_views": [viewer],
            "interactive_items": lambda: proxies(input_widget),
            "interactive_widgets": lambda: as_list(input_widget),
        },
        {
            "widget": start_button,
            "text": "Click the input node's start button to process the selected "
            "input files through the connected pipeline.",
            "requires_completion": True,
            "interactive_views": [viewer],
            "interactive_items": lambda: proxies(start_button),
            "interactive_widgets": lambda: as_list(start_button),
        },
        {
            "widget": main_window.console_dock,
            "text": "Here you can view the output of the processing steps.",
        },
        {
            "widget": main_window.menuBar(),
            "text": "Add code with Plugins > Import Functions... > Load File, "
            "drop a Python file or code onto the canvas, or paste with Ctrl+V.",
        },
        {
            "widget": viewer,
            "text": "<p>Click <b>Import crop example</b> to try this function:</p>"
            f"<pre>{escape(WELCOME_CROP_CODE)}</pre>",
            "action_text": "Import crop example",
            "action": import_crop_example,
            "is_complete": lambda: importer is not None,
            "cleanup": cleanup_crop_example,
        },
        {
            "widget": viewer,
            "text": "Review crop_raw's inputs, outputs and parameters, then click "
            "Save to load the plugin. Only save code you trust.",
            "interactive_widgets": lambda: [importer] if importer is not None else [],
            "is_complete": lambda: plugin_name in ct.plugins,
        },
        {
            "widget": lambda: function_node(),
            "text": "Right-click the canvas or the filter's raw output "
            "and choose crop_raw.",
            "is_complete": lambda: crop_node() is not None,
            "interactive_views": [viewer],
            "interactive_items": crop_source_ports,
        },
        {
            "widget": crop_node,
            "text": "Connect the filter's raw output to crop_raw's raw input.",
            "is_complete": crop_connected,
            "interactive_views": [viewer],
            "interactive_items": crop_connection_ports,
        },
        {
            "widget": main_window.menuBar(),
            "text": "The Plugins menu also loads existing plugins from a path, "
            "module or GitHub.",
        },
        {"widget": viewer, "text": "This concludes the welcome tour."},
    ]


def _load_welcome_plugin(ct: "Controller") -> Callable[[], None]:
    """Load the example plugin for this tour and return its session cleanup."""
    previous_plugins = ct.plugins.copy()
    previous_functions = ct.function_meta.copy()
    previous_meta = deepcopy(ct.get("plugin_meta", {}))
    viewer = ct.viewer

    def cleanup() -> None:
        if viewer is not None:
            for node in list(viewer.function_nodes.values()):
                if node.name is None:
                    continue
                metadata = ct.function_meta.get(node.name.split("-")[0], {})
                if (
                    metadata.get("plugin") == "example_plugin"
                    or metadata.get("plugin") not in previous_plugins
                ):
                    viewer.remove_node(node, force=True)
            ct._unload_plugin_session("example_plugin")
            ct.plugins.clear()
            ct.function_meta.clear()
        ct.plugins.update(previous_plugins)
        ct.function_meta.update(previous_functions)
        ct.set("plugin_meta", previous_meta)
        if viewer is not None:
            viewer.refresh_node_picker()

    try:
        ct.plugins.clear()
        ct.function_meta.clear()
        ct.set("plugin_meta", {})
        plugin = import_module("mne_nodes.extra.example_plugin")
        ct.load_plugin(
            plugin,
            "example_plugin",
            {
                "config_path": WELCOME_CONFIG_PATH.with_name(
                    "example_plugin_config.json"
                ),
                "script_path": WELCOME_CONFIG_PATH.with_name("example_plugin.py"),
                "plugin_type": "path",
            },
        )
        if ct.viewer is not None:
            ct.viewer.refresh_node_picker()
    except Exception:
        cleanup()
        raise
    return cleanup


def _ensure_welcome_sample(
    ct: "Controller", main_window: "MainWindow", *, root: Path | None = None
) -> None:
    """Reuse sample data or prepare it at an explicitly selected destination."""

    def is_sample(root: Path | None) -> bool:
        return (
            root is not None
            and ct._read_bids_dataset_name(root) == "sample-dataset"
            and any(
                (root / "sub-01" / "ses-01" / "meg").glob(
                    "*task-audiovisual_run-1*_meg.fif"
                )
            )
        )

    selected_root = root
    root = root or ct.bids_root
    if root is None or (selected_root is None and not is_sample(root)):
        root = Path(
            ct.settings.get(
                "sample_bids_root", Path.home() / "mne_data" / "mne-nodes-sample-bids"
            )
        )
    if not is_sample(root):
        dialog = WorkerDialog(
            main_window,
            function=load_sample_bids,
            title="Loading Sample BIDS Data",
            show_console=True,
            blocking=True,
            return_exception=True,
            bids_root=root,
        )
        if isinstance(dialog.return_value, ExceptionTuple):
            raise dialog.return_value[1]
        if not is_sample(root):
            raise RuntimeError("Sample BIDS data was not successfully written.")
    ct.settings.set("sample_bids_root", root)
    if ct.bids_root != root:
        ct._activate_bids_root(root)
    else:
        ct.set("bids_dataset_name", ct._read_bids_dataset_name(root))


def start_welcome_tour(
    ct: "Controller", main_window: "MainWindow"
) -> WelcomeTour | None:
    """Ask the user, load a disposable demo pipeline and start the tour.

    The packaged ``Welcome_pipeline.json`` is copied to a temporary directory so
    the tour never writes to the package. The copy is removed when the tour ends.
    Sample BIDS data is prepared before loading the demo and reused on later tours.
    If root confirmation selects another destination, sample data is prepared
    there before the demo nodes are rebuilt.
    Initially only ``example_plugin`` is available. The hands-on import task
    saves its crop plugin in the same temporary directory. Both demo plugins are
    removed and existing plugins restored on completion or cancellation without
    changing disabled settings.
    Returns None when the user declines.
    """
    if not ask_user("Would you like to start the welcome tour?", parent=main_window):
        return None
    _ensure_welcome_sample(ct, main_window)
    demo_directory = TemporaryDirectory(prefix="mne-nodes-welcome-")
    demo_config = Path(demo_directory.name) / WELCOME_CONFIG_PATH.name
    shutil.copyfile(WELCOME_CONFIG_PATH, demo_config)
    # Loading would otherwise remember the demo as the user's last pipeline.
    previous_config_path = ct.settings.get("config_path", None)
    cleanup_plugin = None
    try:
        try:
            ct._apply_config_path(
                demo_config,
                prepare_bids_root=lambda: _ensure_welcome_sample(
                    ct, main_window, root=ct.bids_root
                ),
            )
        finally:
            ct.settings.set("config_path", previous_config_path)
        cleanup_plugin = _load_welcome_plugin(ct)
        tour = WelcomeTour(
            main_window,
            build_welcome_steps(
                ct, main_window, plugin_directory=Path(demo_directory.name)
            ),
        )
    except Exception:
        if cleanup_plugin is not None:
            cleanup_plugin()
        demo_directory.cleanup()
        raise
    tour._cleanup_demo_plugin = cleanup_plugin
    tour.demo_directory = demo_directory

    def process_started() -> None:
        tour.complete_task(7)

    main_window.console_dock.process_started.connect(process_started)

    def disconnect_process_started() -> None:
        main_window.console_dock.process_started.disconnect(process_started)

    tour._disconnect_process_started = disconnect_process_started
    return tour
