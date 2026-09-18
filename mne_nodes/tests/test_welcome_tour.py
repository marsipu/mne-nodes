from qtpy.QtCore import QPoint, QRectF
from qtpy.QtWidgets import QGraphicsRectItem, QGraphicsScene, QGraphicsView, QMainWindow

from mne_nodes.gui.welcome_tour import (
    WELCOME_TOUR_PADDING,
    WelcomeTour,
    WelcomeTourWidget,
)


def test_compute_highlight_rect_for_graphics_item(qtbot):
    main_window = QMainWindow()
    view = QGraphicsView(main_window)
    scene = QGraphicsScene(view)
    item = QGraphicsRectItem(QRectF(10, 20, 30, 40))
    scene.addItem(item)
    view.setScene(scene)
    main_window.setCentralWidget(view)
    main_window.resize(200, 200)
    main_window.show()
    qtbot.addWidget(main_window)

    tour = WelcomeTour.__new__(WelcomeTour)
    tour.main_window = main_window

    actual = tour.compute_highlight_rect(item)
    view_rect = view.mapFromScene(item.sceneBoundingRect()).boundingRect()
    top_left = view.viewport().mapTo(main_window, view_rect.topLeft())
    expected = view_rect.adjusted(
        top_left.x() - view_rect.x() - WELCOME_TOUR_PADDING,
        top_left.y() - view_rect.y() - WELCOME_TOUR_PADDING,
        top_left.x() - view_rect.x() + WELCOME_TOUR_PADDING,
        top_left.y() - view_rect.y() + WELCOME_TOUR_PADDING,
    )
    assert actual == expected


def test_tour_widgets_follow_main_window(qtbot):
    main_window = QMainWindow()
    main_window.resize(200, 200)
    main_window.show()
    qtbot.addWidget(main_window)

    tour = WelcomeTour(main_window, [{"widget": main_window, "text": "Test"}])
    overlay_position = tour.overlay.mapToGlobal(QPoint(0, 0))
    widget_position = tour.widget.mapToGlobal(QPoint(0, 0))

    main_window.move(main_window.pos() + QPoint(20, 20))
    qtbot.wait(50)

    assert tour.overlay.mapToGlobal(QPoint(0, 0)) == overlay_position + QPoint(20, 20)
    assert tour.widget.mapToGlobal(QPoint(0, 0)) == widget_position + QPoint(20, 20)


def test_compute_highlight_path_uses_widget_rect_and_standard_padding(qtbot):
    main_window = QMainWindow()
    main_window.resize(200, 200)
    main_window.show()
    qtbot.addWidget(main_window)

    tour = WelcomeTour.__new__(WelcomeTour)
    tour.main_window = main_window
    path = tour.compute_highlight_path(main_window)

    assert path.boundingRect().toRect() == main_window.rect().adjusted(
        -WELCOME_TOUR_PADDING,
        -WELCOME_TOUR_PADDING,
        WELCOME_TOUR_PADDING,
        WELCOME_TOUR_PADDING,
    )


def test_graphics_item_highlight_updates_after_scroll(qtbot):
    main_window = QMainWindow()
    view = QGraphicsView(main_window)
    scene = QGraphicsScene(view)
    item = QGraphicsRectItem(QRectF(100, 20, 30, 40))
    scene.addItem(item)
    view.setScene(scene)
    view.setSceneRect(0, 0, 500, 200)
    main_window.setCentralWidget(view)
    main_window.resize(200, 200)
    main_window.show()
    qtbot.addWidget(main_window)

    tour = WelcomeTour(main_window, [{"widget": item, "text": "Test"}])
    before_path = tour.overlay.highlight_path
    assert before_path is not None
    before = before_path.boundingRect()
    view.horizontalScrollBar().setValue(50)
    qtbot.wait(50)

    after_path = tour.overlay.highlight_path
    assert after_path is not None
    after = after_path.boundingRect()
    assert after.x() < before.x()


def test_tour_makes_offscreen_graphics_item_visible(qtbot):
    main_window = QMainWindow()
    view = QGraphicsView(main_window)
    scene = QGraphicsScene(view)
    item = QGraphicsRectItem(QRectF(400, 20, 30, 40))
    scene.addItem(item)
    view.setScene(scene)
    view.setSceneRect(0, 0, 500, 200)
    main_window.setCentralWidget(view)
    main_window.resize(200, 200)
    main_window.show()
    qtbot.addWidget(main_window)

    tour = WelcomeTour(main_window, [{"widget": item, "text": "Test"}])
    tour.widget.resize(120, 100)
    tour.refresh()
    item_view_rect = view.mapFromScene(item.sceneBoundingRect()).boundingRect()

    assert view.viewport().rect().intersects(item_view_rect)
    assert main_window.rect().contains(tour.widget.geometry())

    widget_rect = tour.widget.geometry()
    highlight_path = tour.overlay.highlight_path
    assert highlight_path is not None
    assert not widget_rect.intersects(highlight_path.boundingRect().toRect())


def test_welcome_tour_widget_uses_palette_accent(qtbot):
    widget = WelcomeTourWidget()
    qtbot.addWidget(widget)

    assert "palette(highlight)" in widget.styleSheet()
    assert widget.graphicsEffect() is not None
