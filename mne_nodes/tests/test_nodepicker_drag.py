from qtpy.QtCore import QPoint

from mne_nodes.gui.gui_utils import mouseDragBetween


def test_drag_function_from_picker_to_viewer(main_window, qtbot):
    picker = main_window.node_picker
    viewer = main_window.viewer

    view = picker.functions_view
    model = view.model()
    # Ensure at least one function available
    assert model.rowCount() > 0
    # Preselect first row to ensure model supplies indexes for drag
    view.selectRow(0)
    # Pick the first function row name
    fname = model._data.index[0]  # type: ignore[attr-defined]
    # Source position: center of first row rect
    index0 = model.createIndex(0, 0)
    rect = view.visualRect(index0)
    pos_from = rect.center()

    # Target position: center of viewer viewport
    target = viewer.viewport()
    pos_to = target.rect().center()

    # Perform drag
    mouseDragBetween(
        view.viewport(),
        QPoint(pos_from.x(), pos_from.y()),
        target,
        QPoint(pos_to.x(), pos_to.y()),
    )
    qtbot.wait(200)

    # Verify function node created
    node = None
    try:
        node = viewer.node(node_name=fname)
    except KeyError:
        pass
    assert node is not None


essential_input_types = ["raw"]


def test_drag_input_from_picker_to_viewer(main_window, qtbot):
    picker = main_window.node_picker
    viewer = main_window.viewer

    view = picker.inputs_view
    model = view.model()
    assert model.rowCount() > 0

    # Track total nodes before
    before_nodes = len(viewer.nodes)

    # Preselect first row
    view.selectRow(0)
    index0 = model.createIndex(0, 0)
    rect = view.visualRect(index0)
    pos_from = rect.center()

    target = viewer.viewport()
    pos_to = target.rect().center()

    mouseDragBetween(
        view.viewport(),
        QPoint(pos_from.x(), pos_from.y()),
        target,
        QPoint(pos_to.x(), pos_to.y()),
    )
    qtbot.wait(200)

    after_nodes = len(viewer.nodes)
    assert after_nodes > before_nodes
