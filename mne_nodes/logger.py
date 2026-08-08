"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

from __future__ import annotations

import logging
from pathlib import Path

from mne_nodes.pipeline.settings import Settings

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


class FileLockFilter(logging.Filter):
    def filter(self, record):
        # Your filter logic here. For example:
        return "lock" not in record.getMessage().lower()


def init_logging(debug_mode: bool = False) -> None:
    """Initialize Root Logger.

    Idempotent: replaces existing handlers named 'console'/'file' to avoid
    duplicate outputs when called multiple times (e.g., in tests).
    """
    logger = get_logger()
    if debug_mode:
        logger.setLevel(logging.DEBUG)
        fmt = "{asctime} [{levelname}] {module}.{funcName}: {message}"
    else:
        logger.setLevel(Settings().get("log_level", default=logging.INFO))
        fmt = "[{levelname}] {message}"

    # Format console handler
    date_fmt = "%H:%M:%S"
    formatter = logging.Formatter(fmt, date_fmt, style="{")
    console_handler = logging.StreamHandler()
    console_handler.set_name("console")
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Format file handler
    logging_path = Settings().get("log_file_path") or Path.home() / "mne_nodes.log"
    file_handler = logging.FileHandler(logging_path, mode="w", encoding="utf-8")
    file_handler.set_name("file")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Add Filter
    logger.addFilter(FileLockFilter())

    # Hide filelock logging
    logging.getLogger("filelock").setLevel(logging.INFO)
