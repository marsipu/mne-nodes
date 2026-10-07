"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

from mne_nodes.gui.node.base_node import BaseNode


class ExportNode(BaseNode):
    """This node provides a way to export the data."""

    # ToDo:
    # - Create a way to export the data to a file or a database
    def __init__(self, ct, **kwargs):
        super().__init__(ct, **kwargs)
        self.name = "Export Node"
