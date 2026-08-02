"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

from __future__ import annotations

import logging

_LOGGER_NAME = "mne_nodes"


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a package logger or one of its child loggers."""
    if not name:
        return logging.getLogger(_LOGGER_NAME)

    module_name = name.removeprefix("mne_nodes.")
    if module_name == "mne_nodes":
        module_name = ""

    full_name = _LOGGER_NAME if not module_name else f"{_LOGGER_NAME}.{module_name}"
    return logging.getLogger(full_name)


logger = get_logger()
