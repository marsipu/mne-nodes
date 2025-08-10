"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""


def test_node_start(nodeviewer_extended, qtbot):
    nodeviewer_extended.show()
    nodeviewer_extended.input_node("raw").start()
