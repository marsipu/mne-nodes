"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import json
from datetime import datetime
from pathlib import Path

import numpy as np


def encode_tuples(input_dict):
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

    def default(self, o):
        if isinstance(o, np.integer):
            return int(o)
        elif isinstance(o, np.floating):
            return float(o)
        # Only onedimensional arrays are supported
        elif isinstance(o, np.ndarray):
            return {"numpy_array_type": o.tolist()}
        elif isinstance(o, datetime):
            return {"datetime_type": o.strftime(datetime_format)}
        elif isinstance(o, set):
            return {"set_type": list(o)}
        elif isinstance(o, Path):
            return {"path_type": str(o)}
        else:
            return super().default(o)

    def encode(self, o):
        # Also encode tuples (not captured by default())
        new_o = encode_tuples(o)
        return super().encode(new_o)

    def iterencode(self, o, _one_shot=False):
        # Also encode tuples (not captured by default())
        new_o = encode_tuples(o)
        return super().iterencode(new_o, _one_shot=_one_shot)


def type_json_hook(obj):
    if "numpy_int" in obj.keys():
        return obj["numpy_int"]
    elif "numpy_float" in obj.keys():
        return obj["numpy_float"]
    # Only onedimensional arrays are supported
    elif "numpy_array_type" in obj.keys():
        return np.asarray(obj["numpy_array_type"])
    elif "datetime_type" in obj.keys():
        return datetime.strptime(obj["datetime_type"], datetime_format)
    elif "tuple_type" in obj.keys():
        return tuple(obj["tuple_type"])
    elif "set_type" in obj.keys():
        return set(obj["set_type"])
    elif "path_type" in obj.keys():
        return Path(obj["path_type"])
    else:
        return obj
