"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

from mne_nodes.gui.node.base_node import BaseNode


class ExpressionNode(BaseNode):
    """This node is like FunctionWidget, it evaluates expressions and outputs them.
    Output is dynamically changed with expression (assigned reference-name) and
    data-type (assigned reference-name).
    """

    def __init__(self, ct, **kwargs):
        super().__init__(ct, **kwargs)
        self.name = "Expression Node"
