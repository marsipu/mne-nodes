"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""


def test_node_start(main_window):
    start_node = main_window.viewer.input_node(data_type="raw")
    start_node.start()
