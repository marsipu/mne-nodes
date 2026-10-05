import pytest
from qtpy.QtCore import QEvent, QPoint, QPointF, QRectF, Qt
from qtpy.QtGui import (
    QAction,
    QColor,
    QKeyEvent,
    QKeySequence,
    QMouseEvent,
    QPainterPath,
    QPalette,
)
from qtpy.QtWidgets import (
    QApplication,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QMainWindow,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
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


def test_tour_does_not_zoom_or_pan_to_graphics_item(qtbot):
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
    transform = view.transform()
    horizontal_scroll = view.horizontalScrollBar().value()
    vertical_scroll = view.verticalScrollBar().value()

    tour = WelcomeTour(main_window, [{"widget": item, "text": "Test"}])
    tour.widget.resize(120, 100)
    tour.refresh()

    assert view.transform() == transform
    assert view.horizontalScrollBar().value() == horizontal_scroll
    assert view.verticalScrollBar().value() == vertical_scroll
    assert main_window.rect().contains(tour.widget.geometry())
    tour.finish()


def test_welcome_tour_widget_uses_palette_accent(qtbot):
    widget = WelcomeTourWidget()
    qtbot.addWidget(widget)

    assert "palette(highlight)" in widget.styleSheet()
    assert widget.graphicsEffect() is not None


@pytest.mark.parametrize("background", ["#202020", "#f0f0f0"])
def test_tour_panel_paints_opaque_theme_background(qtbot, background):
    original_palette = QApplication.palette()
    palette = QPalette(original_palette)
    palette.setColor(QPalette.ColorRole.Base, QColor(background))
    QApplication.setPalette(palette)
    try:
        widget = WelcomeTourWidget()
        qtbot.addWidget(widget)
        widget.show()
        qtbot.wait(10)
        image = widget.grab().toImage()
        color = image.pixelColor(8, widget.height() // 2)
        assert color.alpha() == 255
        assert color == QColor(background)
    finally:
        QApplication.setPalette(original_palette)


@pytest.mark.parametrize(
    "target_rect,side",
    [
        (QRectF(30, 250, 100, 100), "right"),
        (QRectF(850, 250, 100, 100), "left"),
        (QRectF(20, 20, 960, 100), "below"),
        (QRectF(20, 650, 960, 100), "above"),
    ],
)
def test_panel_is_adjacent_to_target_and_inside_window(qtbot, target_rect, side):
    main_window = QMainWindow()
    qtbot.addWidget(main_window)
    main_window.resize(1000, 800)
    main_window.show()
    tour = WelcomeTour(main_window, [{"widget": main_window, "text": "Test"}])
    try:
        path = QPainterPath()
        path.addRect(target_rect)
        tour._move_widget_into_window(path)
        panel = tour.widget.geometry()
        target = target_rect.toRect()
        assert main_window.rect().adjusted(8, 8, -8, -8).contains(panel)
        assert not panel.intersects(target)
        assert panel.height() >= tour.widget.size_for_width(panel.width()).height()
        if side == "right":
            assert panel.left() == target.right() + 20
            assert abs(panel.center().y() - target.center().y()) <= 1
        elif side == "left":
            assert panel.right() == target.left() - 20
            assert abs(panel.center().y() - target.center().y()) <= 1
        elif side == "below":
            assert panel.top() == target.bottom() + 20
            assert abs(panel.center().x() - target.center().x()) <= 1
        else:
            assert panel.bottom() == target.top() - 20
            assert abs(panel.center().x() - target.center().x()) <= 1
    finally:
        tour.finish()


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


def test_panel_changes_side_when_target_moves_to_window_edge(qtbot):
    main_window = QMainWindow()
    qtbot.addWidget(main_window)
    main_window.resize(1000, 800)
    target = QPushButton("Target", main_window)
    target.setGeometry(30, 20, 100, 50)
    main_window.show()
    tour = WelcomeTour(
        main_window,
        [
            {"widget": target, "text": "Follow this target"},
            {"widget": main_window, "text": "End"},
        ],
    )
    try:
        assert tour.widget.geometry().left() > target.geometry().right()
        target.move(850, 720)
        qtbot.waitUntil(
            lambda: tour.widget.geometry().right() < target.geometry().left()
        )
        assert (
            main_window.rect().adjusted(8, 8, -8, -8).contains(tour.widget.geometry())
        )
        assert not tour.widget.geometry().intersects(target.geometry())
    finally:
        tour.finish()


def test_final_next_button_finishes_tour(qtbot):
    main_window = QMainWindow()
    qtbot.addWidget(main_window)
    main_window.show()
    tour = WelcomeTour(
        main_window,
        [
            {"widget": main_window, "text": "First step"},
            {"widget": main_window, "text": "Last step"},
        ],
    )
    finished = []
    tour.finished.connect(lambda: finished.append(True))
    try:
        assert tour.widget.next_btn.text() == "Next"
        assert not any(
            button.text() == "Finish"
            for button in tour.widget.findChildren(QPushButton)
        )

        tour.next_step()
        assert tour.index == 1
        assert tour.widget.next_btn.text() == "Finished"
        assert not tour.overlay.isVisible()
        tour.prev_step()
        assert tour.overlay.isVisible()
        tour.next_step()
        assert not tour.overlay.isVisible()

        tour.next_step()
        assert finished == [True]
    finally:
        tour.finish()


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
    transform = view.transform()
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
        assert view.transform() == transform
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
        assert view.transform() == transform
        tour.next_step()
        assert tour.index == 1
        assert tour._refresh_timer.isActive()
    finally:
        tour.finish()


def test_task_predicate_feedback_and_undo(qtbot):
    """Completion queues advancement, but undo before the transition cancels it."""
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
        next_button = tour.widget.next_btn
        sample = QPoint(next_button.width() // 2, 3)
        disabled_color = next_button.grab().toImage().pixelColor(sample)
        tour.next_step()
        assert tour.index == 0
        state["connected"] = True
        tour.refresh()
        assert completed == [0]
        assert tour.index == 0
        assert tour.widget.next_btn.isEnabled()
        assert next_button.grab().toImage().pixelColor(sample) != disabled_color
        assert "Task completed!" in tour.widget.status_label.text()
        tour.refresh()
        assert completed == [0]

        state["connected"] = False
        qtbot.waitUntil(lambda: not tour._pending_advance.isActive())
        assert tour.index == 0
        assert not tour.widget.next_btn.isEnabled()
        state["connected"] = True
        qtbot.waitUntil(lambda: tour.index == 1)
        assert completed == [0, 0]
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
    assert not tour._pending_advance.isActive()
    tour.refresh()
    assert completed == [1]


@pytest.mark.parametrize("signal_driven", [False, True])
def test_back_through_completed_tasks_requires_manual_next(qtbot, signal_driven):
    """Revisiting tasks preserves changes and never queues another advance."""
    main_window = QMainWindow()
    qtbot.addWidget(main_window)
    main_window.show()
    state = {"completed": False}
    tasks = [
        {
            "widget": main_window,
            "text": f"Task {index}",
            **(
                {"requires_completion": True}
                if signal_driven
                else {"is_complete": lambda: state["completed"]}
            ),
        }
        for index in range(2)
    ]
    tour = WelcomeTour(
        main_window,
        [
            {"widget": main_window, "text": "Intro"},
            *tasks,
            {"widget": main_window, "text": "End"},
        ],
    )
    completed = []
    tour.task_completed.connect(completed.append)
    try:
        tour.next_step()
        assert not tour.widget.next_btn.isEnabled()
        state["completed"] = True
        if signal_driven:
            tour.complete_task(1)
            tour.complete_task(2)
        qtbot.waitUntil(lambda: tour.index == 3)
        assert completed == [1, 2]

        for index in (2, 1, 0):
            qtbot.mouseClick(tour.widget.prev_btn, Qt.MouseButton.LeftButton)
            qtbot.wait(150)
            assert tour.index == index
            assert not tour._pending_advance.isActive()
            assert state["completed"]

        for index in (1, 2, 3):
            qtbot.mouseClick(tour.widget.next_btn, Qt.MouseButton.LeftButton)
            qtbot.wait(150)
            assert tour.index == index
            assert not tour._pending_advance.isActive()
        assert completed == [1, 2]
    finally:
        tour.finish()


def test_passed_task_can_be_skipped_after_target_and_state_change(qtbot):
    """Later actions must not block navigating through a previously passed step."""
    main_window = QMainWindow()
    qtbot.addWidget(main_window)
    main_window.show()
    state = {"target": main_window, "completed": False}
    tour = WelcomeTour(
        main_window,
        [
            {
                "widget": lambda: state["target"],
                "text": "Task",
                "is_complete": lambda: state["completed"],
            },
            {"widget": main_window, "text": "New task", "is_complete": lambda: False},
        ],
    )
    try:
        state["completed"] = True
        qtbot.waitUntil(lambda: tour.index == 1)
        state["completed"] = False
        state["target"] = None
        tour.prev_step()
        qtbot.wait(150)
        assert tour.index == 0
        assert tour.widget.next_btn.isEnabled()
        assert not tour._pending_advance.isActive()
        assert "Click Next" in tour.widget.status_label.text()
        tour.next_step()
        assert tour.index == 1
        assert not tour.widget.next_btn.isEnabled()
        assert state == {"target": None, "completed": False}
    finally:
        tour.finish()


@pytest.mark.parametrize("precompleted", [False, True])
def test_signal_driven_task_advances_automatically(qtbot, precompleted):
    """Both live completion and completion recorded before entry advance."""
    main_window = QMainWindow()
    qtbot.addWidget(main_window)
    main_window.show()
    tour = WelcomeTour(
        main_window,
        [
            {"widget": main_window, "text": "Info"},
            {"widget": main_window, "text": "Task", "requires_completion": True},
            {"widget": main_window, "text": "Next info"},
        ],
    )
    try:
        if precompleted:
            tour.complete_task(1)
        tour.next_step()
        assert tour.index == 1
        if not precompleted:
            assert not tour.widget.next_btn.isEnabled()
            tour.complete_task(1)
        qtbot.waitUntil(lambda: tour.index == 2)
        assert not tour._pending_advance.isActive()
    finally:
        tour.finish()


@pytest.mark.parametrize("action", ["next", "back", "cancel"])
def test_navigation_cancels_queued_task_advancement(qtbot, action):
    """User navigation must not allow a queued transition to skip another step."""
    main_window = QMainWindow()
    qtbot.addWidget(main_window)
    main_window.show()
    tour = WelcomeTour(
        main_window,
        [
            {"widget": main_window, "text": "First"},
            {"widget": main_window, "text": "Task", "requires_completion": True},
            {"widget": main_window, "text": "Next"},
            {"widget": main_window, "text": "Last"},
        ],
    )
    try:
        tour.show_step(1)
        tour.complete_task(1)
        assert tour._pending_advance.isActive()
        if action == "next":
            tour.next_step()
            assert tour.index == 2
        elif action == "back":
            tour.prev_step()
            assert tour.index == 0
        else:
            qtbot.mouseClick(tour.widget.cancel_btn, Qt.MouseButton.LeftButton)
            assert tour._finished
        assert not tour._pending_advance.isActive()
        index = tour.index
        qtbot.wait(20)
        assert tour.index == index
    finally:
        if action != "cancel":
            tour.finish()


def test_final_task_automatically_finishes_tour(qtbot):
    main_window = QMainWindow()
    qtbot.addWidget(main_window)
    main_window.show()
    tour = WelcomeTour(
        main_window,
        [{"widget": main_window, "text": "Final task", "requires_completion": True}],
    )
    finished = []
    tour.finished.connect(lambda: finished.append(True))
    tour.complete_task(0)
    qtbot.waitUntil(lambda: finished == [True])
    assert not tour.widget.isVisible()


def test_tour_disables_unrelated_controls_and_restores_state(qtbot):
    """Only controls in the active step remain enabled during the tour."""
    main_window = QMainWindow()
    qtbot.addWidget(main_window)
    central = QWidget()
    layout = QVBoxLayout(central)
    allowed_panel = QWidget(central)
    allowed_layout = QVBoxLayout(allowed_panel)
    allowed_button = QPushButton("Task action", allowed_panel)
    initially_disabled = QPushButton("Initially disabled", central)
    initially_disabled.setEnabled(False)
    unrelated_button = QPushButton("Unrelated action", central)
    allowed_layout.addWidget(allowed_button)
    layout.addWidget(allowed_panel)
    layout.addWidget(initially_disabled)
    layout.addWidget(unrelated_button)
    main_window.setCentralWidget(central)
    unrelated_action = QAction("Unrelated shortcut", main_window)
    unrelated_action.setShortcut(QKeySequence("Ctrl+Shift+F12"))
    main_window.addAction(unrelated_action)
    main_window.show()

    tour = WelcomeTour(
        main_window,
        [
            {"widget": main_window, "text": "Introduction"},
            {
                "widget": allowed_panel,
                "text": "Task",
                "interactive_widgets": [allowed_panel],
            },
        ],
    )
    try:
        assert not allowed_button.isEnabled()
        assert not unrelated_button.isEnabled()
        assert unrelated_action.isEnabled()
        assert tour.eventFilter(main_window, QEvent(QEvent.Type.Shortcut))
        key_event = QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier
        )
        assert tour.eventFilter(main_window, key_event)
        tour.next_step()
        assert allowed_button.isEnabled()
        assert not unrelated_button.isEnabled()
        assert unrelated_action.isEnabled()
        assert not tour.eventFilter(allowed_button, key_event)
        assert tour.eventFilter(unrelated_button, key_event)
        assert initially_disabled.isEnabled() is False
        tour.finish()
        assert allowed_button.isEnabled()
        assert unrelated_button.isEnabled()
        assert unrelated_action.isEnabled()
        assert initially_disabled.isEnabled() is False
    finally:
        tour.finish()


def test_interactive_view_does_not_enable_other_interactive_descendants(qtbot):
    """Viewer input stays available without enabling unrelated embedded controls."""
    main_window = QMainWindow()
    qtbot.addWidget(main_window)
    view = QGraphicsView(main_window)
    unrelated_button = QPushButton("Unrelated", view.viewport())
    main_window.setCentralWidget(view)
    main_window.show()
    tour = WelcomeTour(
        main_window,
        [{"widget": view, "text": "Add a node", "interactive_views": [view]}],
    )
    try:
        assert view.isEnabled()
        assert view.viewport().isEnabled()
        assert not unrelated_button.isEnabled()
    finally:
        tour.finish()
    assert unrelated_button.isEnabled()


@pytest.mark.parametrize("keyboard", [False, True])
def test_view_context_menu_and_submenus_remain_interactive(qtbot, keyboard):
    """Popup windows owned by the active view allow mouse and keyboard input."""
    main_window = QMainWindow()
    qtbot.addWidget(main_window)
    view = QGraphicsView(main_window)
    main_window.setCentralWidget(view)
    main_window.show()
    menu = QMenu(view)
    submenu = menu.addMenu("Functions")
    action = submenu.addAction("Create node")
    triggered = []
    action.triggered.connect(lambda: triggered.append(True))
    tour = WelcomeTour(
        main_window,
        [
            {"widget": view, "text": "Info"},
            {"widget": view, "text": "Add a node", "interactive_views": [view]},
        ],
    )
    try:
        assert not menu.isEnabled()
        tour.show_step(1)
        assert menu.isEnabled()
        assert submenu.isEnabled()
        late_submenu = submenu.addMenu("More functions")
        tour.refresh()
        assert late_submenu.isEnabled()
        submenu.popup(view.mapToGlobal(QPoint(20, 20)))
        qtbot.waitUntil(submenu.isVisible)
        if keyboard:
            submenu.setActiveAction(action)
            qtbot.keyClick(submenu, Qt.Key.Key_Return)
        else:
            qtbot.mouseClick(
                submenu,
                Qt.MouseButton.LeftButton,
                pos=submenu.actionGeometry(action).center(),
            )
        assert triggered == [True]
        tour.show_step(0)
        assert not menu.isEnabled()
        assert not submenu.isEnabled()
    finally:
        menu.close()
        tour.finish()


def test_cancel_button_leaves_incomplete_task(qtbot):
    """Cancel restores interaction even when Next is disabled."""
    main_window = QMainWindow()
    qtbot.addWidget(main_window)
    button = QPushButton("Unrelated", main_window)
    main_window.setCentralWidget(button)
    main_window.show()
    tour = WelcomeTour(
        main_window, [{"widget": button, "text": "Task", "is_complete": lambda: False}]
    )
    finished = []
    tour.finished.connect(lambda: finished.append(True))
    assert not tour.widget.next_btn.isEnabled()
    assert tour.widget.cancel_btn.isEnabled()
    qtbot.mouseClick(tour.widget.cancel_btn, Qt.MouseButton.LeftButton)
    assert finished == [True]
    assert button.isEnabled()
    assert not tour._refresh_timer.isActive()
    assert not tour.widget.isVisible()


def test_interactive_view_only_accepts_mouse_input_on_task_items(qtbot):
    """Canvas tasks permit only target-item input outside an active drag."""
    main_window = QMainWindow()
    qtbot.addWidget(main_window)
    view = QGraphicsView(main_window)
    scene = QGraphicsScene(view)
    view.setScene(scene)
    view.setSceneRect(0, 0, 400, 400)
    allowed_item = scene.addRect(QRectF(10, 10, 40, 40))
    scene.addRect(QRectF(200, 200, 40, 40))
    main_window.setCentralWidget(view)
    main_window.resize(400, 400)
    main_window.show()
    tour = WelcomeTour(
        main_window,
        [
            {
                "widget": allowed_item,
                "text": "Use this item",
                "interactive_views": [view],
                "interactive_items": [allowed_item],
            }
        ],
    )
    try:
        allowed_pos = view.mapFromScene(QPointF(20, 20))
        unrelated_pos = view.mapFromScene(QPointF(210, 210))

        def mouse_event(event_type, pos, button, buttons):
            return QMouseEvent(
                event_type,
                QPointF(pos),
                QPointF(view.mapToScene(pos)),
                QPointF(view.viewport().mapToGlobal(pos)),
                button,
                buttons,
                Qt.KeyboardModifier.NoModifier,
            )

        press_allowed = mouse_event(
            QEvent.Type.MouseButtonPress,
            allowed_pos,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
        )
        move_unrelated = mouse_event(
            QEvent.Type.MouseMove,
            unrelated_pos,
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
        )
        release_unrelated = mouse_event(
            QEvent.Type.MouseButtonRelease,
            unrelated_pos,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
        )
        click_unrelated = mouse_event(
            QEvent.Type.MouseButtonPress,
            unrelated_pos,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
        )
        right_click_background = mouse_event(
            QEvent.Type.MouseButtonPress,
            unrelated_pos,
            Qt.MouseButton.RightButton,
            Qt.MouseButton.RightButton,
        )
        right_release_background = mouse_event(
            QEvent.Type.MouseButtonRelease,
            unrelated_pos,
            Qt.MouseButton.RightButton,
            Qt.MouseButton.NoButton,
        )

        assert not tour.eventFilter(view.viewport(), press_allowed)
        assert tour._active_graphics_view is view
        assert not tour.eventFilter(view.viewport(), move_unrelated)
        assert not tour.eventFilter(view.viewport(), release_unrelated)
        assert tour._active_graphics_view is None
        assert tour.eventFilter(view.viewport(), click_unrelated)
        assert not tour.eventFilter(view.viewport(), right_click_background)
        assert not tour.eventFilter(view.viewport(), right_release_background)
        hover_unrelated = mouse_event(
            QEvent.Type.MouseMove,
            unrelated_pos,
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
        )
        assert not tour.eventFilter(view.viewport(), hover_unrelated)
    finally:
        tour.finish()


def test_scene_repaints_do_not_rebuild_static_highlight(qtbot, monkeypatch):
    """Hover and live-pipe repaints must not recompute an unchanged highlight."""
    main_window = QMainWindow()
    qtbot.addWidget(main_window)
    view = QGraphicsView(main_window)
    scene = QGraphicsScene(view)
    view.setScene(scene)
    view.setSceneRect(0, 0, 400, 400)
    item = scene.addRect(QRectF(10, 10, 40, 40))
    other = scene.addRect(QRectF(200, 200, 20, 20))
    main_window.setCentralWidget(view)
    main_window.resize(400, 400)
    main_window.show()
    tour = WelcomeTour(main_window, [{"widget": item, "text": "Item"}])
    calls = []
    original = tour.compute_highlight_path

    def count_compute(target):
        calls.append(target)
        return original(target)

    monkeypatch.setattr(tour, "compute_highlight_path", count_compute)
    try:
        for offset in range(20):
            other.setPos(offset, offset)
            qtbot.wait(5)
        qtbot.wait(50)
        assert calls == []

        item.moveBy(30, 30)
        qtbot.waitUntil(lambda: calls == [item])
        assert tour.overlay.highlight_path == original(item)
    finally:
        tour.finish()


def test_interaction_policy_is_not_reapplied_on_every_refresh(qtbot, monkeypatch):
    main_window = QMainWindow()
    qtbot.addWidget(main_window)
    main_window.show()
    tour = WelcomeTour(main_window, [{"widget": main_window, "text": "Test"}])
    calls = []
    original = tour._apply_interaction_policy

    def count_apply():
        calls.append(True)
        original()

    monkeypatch.setattr(tour, "_apply_interaction_policy", count_apply)
    try:
        tour.refresh()
        tour.refresh()
        assert calls == []

        tour.show_step(0)
        assert calls == [True]
    finally:
        tour.finish()


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
