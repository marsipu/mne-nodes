from qtpy.QtCore import QObject, QPoint, QRect, Qt, Signal
from qtpy.QtGui import QColor, QPainter
from qtpy.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class WelcomeTourOverlay(QWidget):
    """
    Semi-transparent overlay that covers the entire app window.
    It can highlight specific rectangular areas by cutting 'holes' into the overlay.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self.highlight_rect = None
        self.dim_color = QColor(0, 0, 0, 160)

    def set_highlight(self, rect: QRect):
        self.highlight_rect = rect
        self.update()

    def paintEvent(self, event):
        if not self.highlight_rect:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw dimming overlay
        painter.fillRect(self.rect(), self.dim_color)

        # Cut out highlight area
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        painter.fillRect(self.highlight_rect, QColor(0, 0, 0, 0))


class WelcomeTourWidget(QWidget):
    """
    Floating widget that displays text for each step.
    """

    next_clicked = Signal()
    prev_clicked = Signal()
    finished_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setStyleSheet("""
            QWidget {
                background: #ffffff;
                border-radius: 8px;
                border: 1px solid #cccccc;
            }
            QLabel {
                font-size: 14px;
            }
            QPushButton {
                padding: 6px 12px;
            }
        """)

        self.label = QLabel("Welcome step text")
        self.label.setWordWrap(True)

        self.next_btn = QPushButton("Next")
        self.prev_btn = QPushButton("Back")
        self.finish_btn = QPushButton("Finish")

        btns = QHBoxLayout()
        btns.addWidget(self.prev_btn)
        btns.addWidget(self.next_btn)
        btns.addWidget(self.finish_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(self.label)
        layout.addLayout(btns)

        self.prev_btn.clicked.connect(self.prev_clicked)
        self.next_btn.clicked.connect(self.next_clicked)
        self.finish_btn.clicked.connect(self.finished_clicked)

        self.resize(300, 150)

    def set_text(self, text: str):
        self.label.setText(text)


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
    Steps format:
    [
        {
            "widget": some_qwidget,
            "text": "Explanation for this part",
            "padding": 10
        },
        ...
    ]
    """

    def __init__(self, main_window, steps):
        super().__init__()
        self.main_window = main_window
        self.steps = steps
        self.index = 0

        self.overlay = WelcomeTourOverlay(main_window)
        self.overlay.resize(main_window.size())
        self.overlay.show()

        self.widget = WelcomeTourWidget(main_window)
        self.widget.next_clicked.connect(self.next_step)
        self.widget.prev_clicked.connect(self.prev_step)
        self.widget.finished_clicked.connect(self.finish)

        self.show_step(0)

    def compute_highlight_rect(self, widget, padding):
        # Convert widget geometry to global coordinates
        rect = widget.geometry()
        top_left = widget.mapTo(self.main_window, rect.topLeft())
        return QRect(
            top_left.x() - padding,
            top_left.y() - padding,
            rect.width() + padding * 2,
            rect.height() + padding * 2,
        )

    def show_step(self, idx):
        step = self.steps[idx]
        widget = step["widget"]
        text = step["text"]
        padding = step.get("padding", 10)

        # Highlight area
        rect = self.compute_highlight_rect(widget, padding)
        self.overlay.set_highlight(rect)

        # Position tour widget near highlight
        self.widget.set_text(text)
        self.widget.move(rect.bottomLeft() + QPoint(0, 20))
        self.widget.show()

    def next_step(self):
        if self.index < len(self.steps) - 1:
            self.index += 1
            self.show_step(self.index)

    def prev_step(self):
        if self.index > 0:
            self.index -= 1
            self.show_step(self.index)

    def finish(self):
        self.overlay.hide()
        self.widget.hide()
        self.deleteLater()
