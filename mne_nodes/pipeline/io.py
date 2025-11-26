"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import json
from ast import literal_eval
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Generator

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

    def encode(self, o: Any) -> str:
        # Also encode tuples (not captured by default())
        new_o = encode_tuples(o)
        return super().encode(new_o)

    def iterencode(self, o: Any, _one_shot: bool = False) -> Generator[str, None, None]:
        # Also encode tuples (not captured by default())
        new_o = encode_tuples(o)
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
