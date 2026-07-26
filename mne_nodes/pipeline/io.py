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
from typing import Any, Callable, Dict, Iterator

import ijson
import os

import numpy as np
from tqdm import tqdm


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
        """Recursively replace inf, -inf, and nan with typed dict sentinels."""
        if isinstance(obj, float):
            if math.isinf(obj):
                return {"special_float_type": "Infinity" if obj > 0 else "-Infinity"}
            if math.isnan(obj):
                return {"special_float_type": "NaN"}
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

    def iterencode(self, o: Any, _one_shot: bool = False) -> Iterator[str]:
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
        case {"special_float_type": "Infinity"}:
            return math.inf
        case {"special_float_type": "-Infinity"}:
            return -math.inf
        case {"special_float_type": "NaN"}:
            return math.nan
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


def load_json_progress(
    file_path: os.PathLike | str, progress_callback: Callable[[int], None]
) -> dict | list | None:
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
    path = Path(file_path)
    file_size = max(path.stat().st_size, 1)

    with path.open("rb") as f:
        # Keep native JSON float behavior (float), not Decimal.
        parser = ijson.parse(f, use_float=True)

        stack = []
        current_key = None
        root = None

        def _attach_to_parent(value: Any, key: Any) -> None:
            nonlocal root
            if not stack:
                root = value
                return

            parent = stack[-1]["value"]
            if isinstance(parent, list):
                parent.append(value)
            else:
                parent[key] = value

        for _, event, value in parser:
            # progress update
            progress_callback(int(f.tell() / file_size * 100))

            if event == "start_map":
                stack.append({"value": {}, "key": current_key})
                current_key = None

            elif event == "end_map":
                frame = stack.pop()
                obj = type_json_hook(frame["value"])
                _attach_to_parent(obj, frame["key"])
                current_key = None

            elif event == "start_array":
                stack.append({"value": [], "key": current_key})
                current_key = None

            elif event == "end_array":
                frame = stack.pop()
                _attach_to_parent(frame["value"], frame["key"])
                current_key = None

            elif event == "map_key":
                current_key = value

            else:
                # scalar value
                if not stack:
                    root = value
                else:
                    parent = stack[-1]["value"]
                    if isinstance(parent, list):
                        parent.append(value)
                    else:
                        parent[current_key] = value
                current_key = None

        progress_callback(100)
        return root


def json_load_dialog(file_path, parent=None):
    """Load a JSON file with a progress dialog.

    Parameters
    ----------
    file_path : str
        Path to the JSON file.

    Returns
    -------
    dict or list
        The loaded JSON data.
    """
    from mne_nodes.gui.dialogs import ProgressDialog

    progress_dialog = ProgressDialog(
        f"Loading JSON file '{Path(file_path).name}'...", parent=parent
    )
    progress_dialog.show()

    data = load_json_progress(file_path, progress_dialog.set_value)

    progress_dialog.close()
    return data


def load_json_tqdm(file_path: os.PathLike) -> dict | None:
    """
    Load a JSON file and print its contents to the console.

    Parameters
    ----------
    file_path : os.PathLike
        Path to the JSON file.
    """
    pbar = tqdm(total=100, desc=f"Loading JSON file '{Path(file_path).name}'...")
    data = load_json_progress(file_path, lambda x: pbar.update(x - pbar.n))
    pbar.close()
    return data


def load_json(file_path: os.PathLike) -> dict | None:
    from mne_nodes import gui_mode

    if gui_mode:
        return json_load_dialog(file_path)
    else:
        return load_json_tqdm(file_path)
