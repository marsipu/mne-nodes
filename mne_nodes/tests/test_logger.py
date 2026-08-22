"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

from mne_nodes.logger import get_logger, logger


def test_get_logger_root_name():
    assert logger.name == "mne_nodes"
    assert get_logger().name == "mne_nodes"


def test_get_logger_child_name():
    assert get_logger("mne_nodes.pipeline.controller").name == (
        "mne_nodes.pipeline.controller"
    )
