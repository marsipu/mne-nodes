"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

from mne_nodes.pipeline.data_import import import_dataset


def test_node_start(qtbot, main_window, controller):
    import_dataset(controller, "testing")
    controller.selected_inputs.append("testing")
    start_node = main_window.viewer.input_node(data_type="raw")
    with qtbot.waitSignal(main_window.processFinished, timeout=5000) as finished:
        start_node.start()
    assert finished.args[0] == 0
