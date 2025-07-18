"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

from mne_nodes import _object_refs
from mne_nodes.tests._test_utils import _test_wait


def test_init(main_window, qtbot):
    qtbot.waitExposed(main_window)

    qtbot.screenshot(main_window, name="main_window_init")

    main_window.close()

    _test_wait(qtbot, 1000)

    assert _object_refs["main_window"] is None
