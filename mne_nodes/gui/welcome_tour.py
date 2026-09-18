from qtpy.QtCore import QEvent, QObject, QPoint, QRect, QSize, Qt, Signal
from qtpy.QtGui import QColor, QPainter, QPainterPath, QPainterPathStroker, QPalette
from qtpy.QtWidgets import (
    QGraphicsDropShadowEffect,
    QGraphicsItem,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mne_nodes.gui.gui_theme import WELCOME_TOUR_STYLE

WELCOME_TOUR_PADDING = 10


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

    def set_highlight(self, path: QPainterPath):
        self.highlight_path = path
        self.update()

    def paintEvent(self, event):
        if not self.highlight_path:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        dim_path = QPainterPath()
        dim_path.setFillRule(Qt.FillRule.OddEvenFill)
        dim_path.addRect(self.rect())
        dim_path.addPath(self.highlight_path)
        painter.fillPath(dim_path, self.dim_color)


class WelcomeTourWidget(QWidget):
    """
    Floating widget that displays text for each step.
    """

    next_clicked = Signal()
    prev_clicked = Signal()
    finished_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("WelcomeTourWidget")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)

        self.label = QLabel("Welcome step text")
        self.label.setObjectName("tourLabel")
        self.label.setWordWrap(True)

        self.next_btn = QPushButton("Next")
        self.next_btn.setObjectName("nextButton")
        self.prev_btn = QPushButton("Back")
        self.prev_btn.setObjectName("backButton")
        self.finish_btn = QPushButton("Finish")
        self.finish_btn.setObjectName("finishButton")

        btns = QHBoxLayout()
        btns.setSpacing(8)
        btns.addWidget(self.prev_btn)
        btns.addWidget(self.next_btn)
        btns.addWidget(self.finish_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(12)
        layout.addWidget(self.label)
        layout.addLayout(btns)
        self._button_layout = btns
        self._content_layout = layout

        self.prev_btn.clicked.connect(self.prev_clicked)
        self.next_btn.clicked.connect(self.next_clicked)
        self.finish_btn.clicked.connect(self.finished_clicked)

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
        return QSize(width, height)


class WelcomeTour(QObject):
    """
    Controls the tour: steps, overlay, widget positioning, transitions.
    Parameters
    ----------
    main_window : QMainWindow
        The main application window.
    steps : list of dict
        The steps of the tour, each containing "widget", "text", and optional "padding".

    Notes
    -----
    Steps contain ``"widget"`` and ``"text"``. Highlights use the standard
    :data:`WELCOME_TOUR_PADDING` value and the target's own shape.
    """

    def __init__(self, main_window, steps):
        super().__init__()
        self.main_window = main_window
        self.steps = steps
        self.index = 0
        self._observed_objects = []
        self._observed_scrollbars = []
        self._scene = None

        self.overlay = WelcomeTourOverlay(main_window)
        self.overlay.resize(main_window.size())
        self.overlay.show()
        self.overlay.raise_()

        self.widget = WelcomeTourWidget(main_window)
        self.widget.next_clicked.connect(self.next_step)
        self.widget.prev_clicked.connect(self.prev_step)
        self.widget.finished_clicked.connect(self.finish)

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
            scrollbar.valueChanged.disconnect(self.refresh)
        self._observed_scrollbars.clear()
        if self._scene is not None:
            self._scene.changed.disconnect(self.refresh)
            self._scene = None

    def _observe_target(self, target):
        self._clear_observers()
        objects = [self.main_window]
        if isinstance(target, QGraphicsItem):
            view = self._graphics_view(target)
            scene = target.scene()
            objects.extend([view, view.viewport()])
            for scrollbar in (view.horizontalScrollBar(), view.verticalScrollBar()):
                scrollbar.valueChanged.connect(self.refresh)
                self._observed_scrollbars.append(scrollbar)
            self._scene = scene
            scene.changed.connect(self.refresh)
        else:
            objects.append(target)
        for observed in objects:
            observed.installEventFilter(self)
            self._observed_objects.append(observed)

    def _ensure_target_visible(self, target):
        if not isinstance(target, QGraphicsItem):
            return

        view = self._graphics_view(target)
        prepare_tour = getattr(view, "prepare_welcome_tour", None)
        if callable(prepare_tour):
            panel_size = self.widget.size_for_width(self.widget.sizeHint().width())
            prepare_tour(target, panel_size, WELCOME_TOUR_PADDING)
            return
        view.ensureVisible(target, WELCOME_TOUR_PADDING, WELCOME_TOUR_PADDING)

    @staticmethod
    def _placement_regions(bounds, target, gap):
        regions = []
        below_top = target.bottom() + gap
        if below_top <= bounds.bottom():
            regions.append(
                QRect(
                    bounds.left(),
                    below_top,
                    bounds.width(),
                    bounds.bottom() - below_top + 1,
                )
            )
        above_bottom = target.top() - gap
        if above_bottom >= bounds.top():
            regions.append(
                QRect(
                    bounds.left(),
                    bounds.top(),
                    bounds.width(),
                    above_bottom - bounds.top() + 1,
                )
            )
        right_left = target.right() + gap
        if right_left <= bounds.right():
            regions.append(
                QRect(
                    right_left,
                    bounds.top(),
                    bounds.right() - right_left + 1,
                    bounds.height(),
                )
            )
        left_right = target.left() - gap
        if left_right >= bounds.left():
            regions.append(
                QRect(
                    bounds.left(),
                    bounds.top(),
                    left_right - bounds.left() + 1,
                    bounds.height(),
                )
            )
        return regions

    def _move_widget_into_window(self, path):
        bounds = self.main_window.rect().adjusted(8, 8, -8, -8)
        target = path.boundingRect().toRect()
        candidates = self._placement_regions(bounds, target, gap=20) or [bounds]

        available = max(
            candidates, key=lambda candidate: candidate.width() * candidate.height()
        )
        desired_width = max(self.widget.sizeHint().width(), 260)
        width = min(desired_width, available.width())
        height = min(self.widget.size_for_width(width).height(), available.height())
        self.widget.resize(width, height)
        x = available.left()
        y = available.top() + max((available.height() - height) // 2, 0)
        self.widget.move(x, y)

    def eventFilter(self, watched, event):
        if event.type() in (
            QEvent.Type.Move,
            QEvent.Type.Resize,
            QEvent.Type.Show,
            QEvent.Type.LayoutRequest,
        ):
            self.refresh()
        return super().eventFilter(watched, event)

    def refresh(self):
        step = self.steps[self.index]
        target = step["widget"]
        path = self.compute_highlight_path(target)
        self.overlay.resize(self.main_window.size())
        self.overlay.set_highlight(path)
        self._move_widget_into_window(path)
        self.widget.raise_()

    def show_step(self, idx):
        self.index = idx
        step = self.steps[idx]
        self._observe_target(step["widget"])
        self.widget.set_text(step["text"])
        self.widget.show()
        self._ensure_target_visible(step["widget"])
        self.refresh()

    def next_step(self):
        if self.index < len(self.steps) - 1:
            self.show_step(self.index + 1)

    def prev_step(self):
        if self.index > 0:
            self.show_step(self.index - 1)

    def finish(self):
        self._clear_observers()
        self.overlay.hide()
        self.widget.hide()
        self.deleteLater()
