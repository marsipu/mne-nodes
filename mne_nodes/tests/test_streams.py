"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import logging

from mne_nodes.pipeline.streams import deinit_streams, init_logging


def _named_handlers(logger: logging.Logger, name: str) -> list[logging.Handler]:
    return [handler for handler in logger.handlers if handler.get_name() == name]


def test_init_logging_is_idempotent(settings, tmp_path):
    """Repeated init_logging calls must not duplicate named handlers."""
    logger = logging.getLogger()
    settings.set("log_file_path", tmp_path / "mne_nodes_test.log")

    try:
        init_logging()
        first_console_handlers = _named_handlers(logger, "console")
        first_file_handlers = _named_handlers(logger, "file")

        assert len(first_console_handlers) == 1
        assert len(first_file_handlers) == 1

        init_logging()
        second_console_handlers = _named_handlers(logger, "console")
        second_file_handlers = _named_handlers(logger, "file")

        assert len(second_console_handlers) == 1
        assert len(second_file_handlers) == 1
        assert second_console_handlers[0] is not first_console_handlers[0]
        assert second_file_handlers[0] is not first_file_handlers[0]
    finally:
        for handler in list(logger.handlers):
            if handler.get_name() in {"console", "file"}:
                logger.removeHandler(handler)
                handler.close()
        deinit_streams()
