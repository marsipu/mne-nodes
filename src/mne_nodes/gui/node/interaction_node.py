"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

from mne_nodes.gui.node.base_node import BaseNode


class InteractionNode(BaseNode):
    """This node provides a way to directly interact with the data."""

    # ToDo:
    # - Create a Console-like editor with inputs from input-node
    def __init__(self, ct, **kwargs):
        super().__init__(ct, **kwargs)
        self.name = "Interaction Node"
