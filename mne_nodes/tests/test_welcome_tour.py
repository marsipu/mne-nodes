import pytest
from qtpy.QtCore import QPoint, QRectF
from qtpy.QtWidgets import (
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QMainWindow,
    QPushButton,
)

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


def test_finish_notifies_once_after_removing_observers(qtbot):
    """Completion handlers can safely replace targets without stale observers."""
    main_window = QMainWindow()
    qtbot.addWidget(main_window)
    main_window.show()
    tour = WelcomeTour(main_window, [{"widget": main_window, "text": "Test"}])
    finished = []

    def on_finished():
        assert not tour._observed_objects
        assert not tour.overlay.isVisible()
        assert not tour.widget.isVisible()
        finished.append(True)

    tour.finished.connect(on_finished)
    tour.finish()
    tour.finish()

    assert finished == [True]


def test_dynamic_target_created_moved_removed_and_replaced(qtbot):
    """Resolve a live target rather than retaining a removed graphics item."""
    main_window = QMainWindow()
    qtbot.addWidget(main_window)
    view = QGraphicsView(main_window)
    scene = QGraphicsScene(view)
    view.setScene(scene)
    view.setSceneRect(0, 0, 600, 400)
    main_window.setCentralWidget(view)
    main_window.resize(600, 400)
    main_window.show()
    targets = []
    tour = WelcomeTour(
        main_window,
        [
            {
                "widget": lambda: targets[0] if targets else None,
                "text": "Create a node",
            },
            {"widget": main_window, "text": "Next"},
        ],
    )
    try:
        assert tour.overlay.highlight_path.isEmpty()
        assert not tour.widget.next_btn.isEnabled()
        tour.next_step()
        assert tour.index == 0

        item = QGraphicsRectItem(QRectF(20, 20, 30, 40))
        scene.addItem(item)
        targets.append(item)
        qtbot.waitUntil(lambda: tour._target is item)
        assert tour.overlay.highlight_path == tour.compute_highlight_path(item)
        assert tour.widget.next_btn.isEnabled()
        item.moveBy(40, 30)
        qtbot.waitUntil(
            lambda: tour.overlay.highlight_path == tour.compute_highlight_path(item)
        )

        targets.clear()
        scene.removeItem(item)
        qtbot.waitUntil(lambda: tour._target is None)
        assert tour.overlay.highlight_path.isEmpty()
        assert not tour.widget.next_btn.isEnabled()

        replacement = QGraphicsRectItem(QRectF(60, 30, 50, 50))
        scene.addItem(replacement)
        targets.append(replacement)
        qtbot.waitUntil(lambda: tour._target is replacement)
        tour.next_step()
        assert tour.index == 1
        assert not tour._refresh_timer.isActive()
    finally:
        tour.finish()


def test_task_predicate_feedback_and_undo(qtbot):
    """Task checks gate Next and report each transition to successful state."""
    main_window = QMainWindow()
    qtbot.addWidget(main_window)
    main_window.show()
    state = {"connected": False}
    tour = WelcomeTour(
        main_window,
        [
            {
                "widget": main_window,
                "text": "Connect nodes",
                "is_complete": lambda: state["connected"],
            },
            {"widget": main_window, "text": "Next"},
        ],
    )
    completed = []
    tour.task_completed.connect(completed.append)
    try:
        assert not tour.widget.next_btn.isEnabled()
        assert tour.widget.status_label.text() == "Complete the task to continue."
        tour.next_step()
        assert tour.index == 0
        state["connected"] = True
        qtbot.waitUntil(lambda: completed == [0])
        assert tour.widget.next_btn.isEnabled()
        assert "Task completed!" in tour.widget.status_label.text()
        tour.refresh()
        assert completed == [0]

        state["connected"] = False
        qtbot.waitUntil(lambda: not tour.widget.next_btn.isEnabled())
        state["connected"] = True
        qtbot.waitUntil(lambda: completed == [0, 0])
        tour.next_step()
        assert tour.index == 1
        assert tour.widget.status_label.isHidden()
        tour.prev_step()
        assert tour.widget.next_btn.isEnabled()
    finally:
        tour.finish()


def test_signal_driven_completion_and_timer_cleanup(qtbot):
    """Completion is addressed to a step so late feedback cannot unlock another."""
    main_window = QMainWindow()
    qtbot.addWidget(main_window)
    main_window.show()
    tour = WelcomeTour(
        main_window,
        [
            {"widget": main_window, "text": "Info"},
            {
                "widget": main_window,
                "text": "Perform action",
                "requires_completion": True,
            },
        ],
    )
    completed = []
    tour.task_completed.connect(completed.append)
    with pytest.raises(IndexError):
        tour.complete_task(2)
    with pytest.raises(ValueError):
        tour.complete_task(0)
    tour.complete_task(1)
    assert completed == []
    tour.next_step()
    assert completed == [1]
    assert tour.widget.next_btn.isEnabled()
    assert tour._refresh_timer.isActive()
    tour.finish()
    assert not tour._refresh_timer.isActive()
    tour.refresh()
    assert completed == [1]


def test_dynamic_embedded_widget_uses_graphics_proxy(qtbot):
    """Embedded parameter widgets must use scene coordinates for highlighting."""
    main_window = QMainWindow()
    qtbot.addWidget(main_window)
    view = QGraphicsView(main_window)
    scene = QGraphicsScene(view)
    view.setScene(scene)
    button = QPushButton("Run")
    proxy = scene.addWidget(button)
    main_window.setCentralWidget(view)
    main_window.show()
    tour = WelcomeTour(main_window, [{"widget": lambda: button, "text": "Run"}])
    try:
        assert tour._target is proxy
        assert tour.overlay.highlight_path == tour.compute_highlight_path(proxy)
    finally:
        tour.finish()
