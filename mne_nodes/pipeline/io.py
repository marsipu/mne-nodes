"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import json
from ast import literal_eval
from datetime import datetime
import math
from pathlib import Path
from typing import Any, Dict, Generator

import ijson
import os

import numpy as np


def encode_tuples(input_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Encode tuples in a dictionary, because JSON does not recognize them."""
    encoded_dict = input_dict.copy()
    for key, value in input_dict.items():
        if isinstance(value, dict):
            encoded_dict[key] = encode_tuples(value)
        else:
            if isinstance(value, tuple):
                encoded_dict[key] = {"tuple_type": value}

    return encoded_dict


datetime_format = "%d.%m.%Y %H:%M:%S"


class TypedJSONEncoder(json.JSONEncoder):
    """Custom JSON Encoder to handle specific types like numpy arrays,
    datetime, etc. Dictionaries are expected to have string-keys."""

    def default(self, o: Any) -> Any:
        match o:
            case o if isinstance(o, np.integer):
                return int(o)
            case o if isinstance(o, np.floating):
                return float(o)
            case o if isinstance(o, np.ndarray):
                return {"numpy_array_type": o.tolist()}
            case datetime():
                return {"datetime_type": o.strftime(datetime_format)}
            case set():
                return {"set_type": list(o)}
            case Path():
                return {"path_type": str(o)}
            case _:
                return super().default(o)

    @staticmethod
    def sanitize_special_floats(obj):
        """Recursively replace inf, -inf, and nan with safe string tokens."""
        if isinstance(obj, float):
            if math.isinf(obj):
                return "Infinity" if obj > 0 else "-Infinity"
            if math.isnan(obj):
                return "NaN"
            return obj

        elif isinstance(obj, dict):
            return {
                k: TypedJSONEncoder.sanitize_special_floats(v) for k, v in obj.items()
            }

        elif isinstance(obj, (list, tuple, set)):
            return [TypedJSONEncoder.sanitize_special_floats(v) for v in obj]

        return obj

    def encode(self, o: Any) -> str:
        # Also encode tuples (not captured by default())
        new_o = encode_tuples(o)
        new_o = self.sanitize_special_floats(new_o)
        return super().encode(new_o)

    def iterencode(self, o: Any, _one_shot: bool = False) -> Generator[str, None, None]:
        # Also encode tuples (not captured by default())
        new_o = encode_tuples(o)
        new_o = self.sanitize_special_floats(new_o)
        return super().iterencode(new_o, _one_shot=_one_shot)


def type_json_hook(obj: Dict[str, Any]) -> Any:
    # Convert keys if converted to string by json
    new_obj = {}
    for key, value in obj.items():
        try:
            literal_key = literal_eval(key)
        except (SyntaxError, ValueError):
            literal_key = key
        new_obj[literal_key] = value
    # Match type specifiers
    match new_obj:
        case value if value == "Infinity":
            return math.inf
        case value if value == "-Infinity":
            return -math.inf
        case value if value == "NaN":
            return math.nan
        case {"numpy_int": value}:
            return value
        case {"numpy_float": value}:
            return value
        case {"numpy_array_type": value}:
            return np.asarray(value)
        case {"datetime_type": value}:
            return datetime.strptime(value, datetime_format)
        case {"tuple_type": value}:
            return tuple(value)
        case {"set_type": value}:
            return set(value)
        case {"path_type": value}:
            return Path(value)
        case _:
            return new_obj


def load_json_progress(file_path, progress_callback):
    """
    Load nested JSON using ijson, calling object_hook for each completed dict.

    Parameters
    ----------
    path : str
        JSON file path.
    progress_callback : callable
        Receives int in percentage (assumes max value is 100).

    Returns
    -------
    dict or list
        Fully reconstructed JSON structure.
    """
    file_size = os.path.getsize(file_path)

    with open(file_path, "rb") as f:
        parser = ijson.parse(f)

        stack = []
        current_key = None
        root = None

        for prefix, event, value in parser:
            # progress update
            progress_callback(int(f.tell() / file_size * 100))

            if event == "start_map":
                obj = {}
                if stack:
                    parent = stack[-1]
                    if isinstance(parent, list):
                        parent.append(obj)
                    else:
                        parent[current_key] = obj
                else:
                    root = obj
                stack.append(obj)
                current_key = None

            elif event == "end_map":
                obj = stack.pop()
                obj = type_json_hook(obj)  # <-- your hook is applied here

                if stack:
                    parent = stack[-1]
                    if isinstance(parent, list):
                        parent[-1] = obj
                    else:
                        parent[current_key] = obj
                current_key = None

            elif event == "start_array":
                arr = []
                if stack:
                    parent = stack[-1]
                    if isinstance(parent, list):
                        parent.append(arr)
                    else:
                        parent[current_key] = arr
                else:
                    root = arr
                stack.append(arr)
                current_key = None

            elif event == "end_array":
                arr = stack.pop()
                if stack:
                    parent = stack[-1]
                    if isinstance(parent, list):
                        parent[-1] = arr
                    else:
                        parent[current_key] = arr
                current_key = None

            elif event == "map_key":
                current_key = value

            else:
                # scalar value
                parent = stack[-1]
                if isinstance(parent, list):
                    parent.append(value)
                else:
                    parent[current_key] = value
                current_key = None

        progress_callback(100)
        return root
