"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

from mne_nodes.pipeline.data_import import import_dataset


def test_node_start(main_window, controller):
    import_dataset(controller, "testing")
    controller.selected_inputs.append("testing")
    start_node = main_window.viewer.input_node(data_type="raw")
    start_node.start()
