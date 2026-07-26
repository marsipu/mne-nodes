"""Shared helpers for parameter GUI widgets."""

from __future__ import annotations

from typing import Any

import numpy as np


def eval_param(param_exp: str) -> Any:
    """Evaluate user expression with numpy available as np.

    Returns None for invalid expressions.
    """
    try:
        return eval(param_exp, {"__builtins__": {}, "np": np})
    except (NameError, SyntaxError, ValueError, TypeError):
        return None


def convert_list_to_string(
    value: Any, unit: str | None = None, string_length: int | None = 30
) -> str:
    """Convert a list to a compact string representation."""
    if isinstance(value, list):
        if unit:
            val_str = ", ".join([f"{item} {unit}" for item in value])
        else:
            val_str = ", ".join([str(item) for item in value])
        if string_length is not None and len(val_str) >= string_length:
            return f"{val_str[:string_length]} ..."
        return val_str
    return str(value)


def convert_dict_to_string(
    value: Any, unit: str | None = None, string_length: int | None = 30
) -> str:
    """Convert a dict to a compact string representation."""
    if isinstance(value, dict):
        if unit:
            val_str = ", ".join([f"{k} {unit}: {v} {unit}" for k, v in value.items()])
        else:
            val_str = ", ".join([f"{k}: {v}" for k, v in value.items()])
        if string_length is not None and len(val_str) >= string_length:
            return f"{val_str[:string_length]} ..."
        return val_str
    return str(value)
