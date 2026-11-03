"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

from pathlib import Path

from qtpy.QtCore import QEvent, QMimeData, QPoint, QPointF, Qt
from qtpy.QtGui import QMouseEvent
from qtpy.QtTest import QTest
from qtpy.QtWidgets import QApplication, QWidget


def is_function_import_mime(mime: QMimeData) -> bool:
    """Recognize external Python-file or code-text import payloads."""
    if mime.hasUrls():
        return bool(mime.urls()) and all(
            url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() == ".py"
            for url in mime.urls()
        )
    return bool(mime.text().strip()) and not mime.text().startswith("mne-nodes/")


def center(widget):
    qr = widget.frameGeometry()
    cp = QApplication.primaryScreen().availableGeometry().center()
    qr.moveCenter(cp)
    widget.move(qr.topLeft())


def set_ratio_geometry(size_ratio, widget):
    """Set the geometry of a widget based on the screen size and a ratio.

    Parameters
    ----------
    size_ratio : float or tuple of float
        Enter the ratio of the current screen size to set the widget size, e.g. (0.5, 0.5) for half the width
        and height of the screen. If a single float is provided, it will be used for both width and height.
    widget : QWidget
        The widget to resize.
    """
    if not isinstance(size_ratio, tuple):
        size_ratio = (size_ratio, size_ratio)
    wratio, hratio = size_ratio
    if widget.screen() is None:
        geometry = QApplication.primaryScreen().availableGeometry()
    else:
        geometry = widget.screen().availableGeometry()
    width = int(geometry.width() * wratio)
    height = int(geometry.height() * hratio)
    widget.resize(width, height)

    return width, height


def invert_rgb_color(color_tuple):
    return tuple(map(lambda i, j: i - j, (255, 255, 255), color_tuple))


def format_color(clr):
    """This converts a hex-color-string to a tuple of RGB-values."""
    if isinstance(clr, str):
        clr = clr.strip("#")
        return tuple(int(clr[i : i + 2], 16) for i in (0, 2, 4))
    return clr


def mouse_interaction(func):
    def wrapper(**kwargs):
        QTest.qWaitForWindowExposed(kwargs["widget"])
        QTest.qWait(10)
        func(**kwargs)
        QTest.qWait(10)

    return wrapper


def _event_positions(widget, pos):
    """Return local and global positions as QPointF for Qt6 mouse events."""
    if widget is None:
        raise ValueError("widget must not be None")
    if pos is None:
        raise ValueError("pos must not be None")
    local_pos = QPointF(pos)
    global_point = widget.mapToGlobal(local_pos.toPoint())
    global_pos = QPointF(global_point)
    return local_pos, global_pos


@mouse_interaction
def mousePress(widget=None, pos=None, button=None, modifier=None):
    if widget is None:
        raise ValueError("widget must not be None")
    if modifier is None:
        modifier = Qt.KeyboardModifier.NoModifier
    if button is None:
        button = Qt.MouseButton.LeftButton
    local_pos, global_pos = _event_positions(widget, pos)
    event = QMouseEvent(
        QEvent.Type.MouseButtonPress, local_pos, global_pos, button, button, modifier
    )
    QApplication.sendEvent(widget, event)


@mouse_interaction
def mouseRelease(widget=None, pos=None, button=None, modifier=None):
    if widget is None:
        raise ValueError("widget must not be None")
    if modifier is None:
        modifier = Qt.KeyboardModifier.NoModifier
    if button is None:
        button = Qt.MouseButton.LeftButton
    local_pos, global_pos = _event_positions(widget, pos)
    event = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        local_pos,
        global_pos,
        button,
        Qt.MouseButton.NoButton,
        modifier,
    )
    QApplication.sendEvent(widget, event)


@mouse_interaction
def mouseMove(widget=None, pos=None, button=None, modifier=None):
    if widget is None:
        raise ValueError("widget must not be None")
    if button is None:
        button = Qt.MouseButton.NoButton
    if modifier is None:
        modifier = Qt.KeyboardModifier.NoModifier
    local_pos, global_pos = _event_positions(widget, pos)
    event = QMouseEvent(
        QEvent.Type.MouseMove,
        local_pos,
        global_pos,
        Qt.MouseButton.NoButton,
        button,
        modifier,
    )
    QApplication.sendEvent(widget, event)


def mouseClick(widget, pos, button, modifier=None):
    mouseMove(widget=widget, pos=pos)
    mousePress(widget=widget, pos=pos, button=button, modifier=modifier)
    mouseRelease(widget=widget, pos=pos, button=button, modifier=modifier)


def mouseDrag(widget, positions, button, modifier=None):
    mouseMove(widget=widget, pos=positions[0])
    mousePress(widget=widget, pos=positions[0], button=button, modifier=modifier)
    for pos in positions[1:]:
        mouseMove(widget=widget, pos=pos, button=button, modifier=modifier)
    # For some reason moeve again to last position
    mouseMove(widget=widget, pos=positions[-1], button=button, modifier=modifier)
    mouseRelease(widget=widget, pos=positions[-1], button=button, modifier=modifier)


def mouseDragBetween(
    widget_from,
    pos_from,
    widget_to,
    pos_to,
    button=Qt.MouseButton.LeftButton,
    modifier=None,
):
    """Drag from one widget to another using low-level mouse events.

    Sends MousePress on source, several MouseMove events with button
    held to trigger startDrag, then moves into target and releases.
    """
    if modifier is None:
        modifier = Qt.KeyboardModifier.NoModifier
    QTest.qWaitForWindowExposed(widget_from.window())
    QTest.qWaitForWindowExposed(widget_to.window())
    # Press on source
    mousePress(widget=widget_from, pos=pos_from, button=button, modifier=modifier)
    # Move within source to exceed drag threshold
    mouseMove(
        widget=widget_from,
        pos=QPoint(pos_from.x() + 30, pos_from.y()),
        button=button,
        modifier=modifier,
    )
    QTest.qWait(10)
    # Move into target widget while holding button
    mouseMove(widget=widget_to, pos=pos_to, button=button, modifier=modifier)
    QTest.qWait(10)
    mouseRelease(widget=widget_to, pos=pos_to, button=button, modifier=modifier)


def edit_font(widget: QWidget, font_size: int, bold: bool = False) -> None:
    font = widget.font()
    font.setPointSize(font_size)
    font.setBold(bold)
    widget.setFont(font)
