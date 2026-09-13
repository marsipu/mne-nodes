"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes

Shared constants/helpers for deriving node metadata (BIDSPath suffixes,
parameter-GUI classes, input/parameter types) from function signatures and
docstrings. Used by the pipeline code generator, the GUI function importer,
and external plugin packages that auto-generate node configuration from
function/class docstrings (e.g. mne-nodes_mne-functions).
"""

import inspect
import re
from ast import literal_eval
from types import NoneType, UnionType
from typing import Union, get_args, get_origin

# BIDSPath suffix for well-known MNE object/port types.
OBJECT_SUFFIXES = {
    "epochs": "epo",
    "evokeds": "ave",
    "covariance": "cov",
    "forward": "fwd",
    "transform": "trans",
    "sourcespaces": "src",
    "averagetfr": "tfr",
    "rawtfr": "tfr",
    "epochstfr": "tfr",
}

# Docstring type-name aliases normalized to a canonical GUI type name.
ARRAY_TYPE_ALIASES = {
    "array-like": "array",
    "array_like": "array",
    "ndarray": "array",
    "np.ndarray": "array",
    "numpy array": "array",
}
ARRAY_CONTAINER_TYPES = ("array",)
COLOR_TYPE_ALIASES = {"color object": "color", "matplotlib color": "color"}
PATH_TYPE_ALIASES = {"path-like": "path", "path_like": "path"}

# Fallback default value for a parameter whose docstring/signature had none.
TYPE_DEFAULTS = {
    "int": 0,
    "float": 0.0,
    "bool": False,
    "str": "",
    "list": [],
    "dict": {},
    "tuple": (0, 0),
    "combo": "",
    "checklist": [],
    "slider": 0.0,
    "path": "",
    "slice": slice(0, 1),
}

# Populated lazily by __getattr__ below, since building it requires importing
# mne_nodes.gui.parameter (Qt widgets), which in turn imports the pipeline
# controller/code-generator; importing that eagerly here would create an
# import cycle for pipeline-only consumers (e.g. code_generation.py) that
# only need OBJECT_SUFFIXES/suffix_for_ports.
_DEFAULT_TYPE_GUIS = None


def _build_default_type_guis():
    from mne_nodes.gui.parameter import (
        ArrayGui,
        BoolGui,
        CallableGui,
        ColorGui,
        ComboGui,
        DataFrameGui,
        DateTimeGui,
        DictGui,
        DualTupleGui,
        FloatGui,
        IntGui,
        ListGui,
        MultiTypeGui,
        PathGui,
        SliceGui,
        StringGui,
        TupleGui,
    )

    return {
        "int": IntGui,
        "float": FloatGui,
        "str": StringGui,
        "bool": BoolGui,
        "list": ListGui,
        "dict": DictGui,
        "object": MultiTypeGui,
        "NoneType": MultiTypeGui,
        "tuple": TupleGui,
        "dual_tuple": DualTupleGui,
        "combo": ComboGui,
        "path": PathGui,
        "slice": SliceGui,
        "DataFrame": DataFrameGui,
        "array": ArrayGui,
        "color": ColorGui,
        "function": CallableGui,
        "callable": CallableGui,
        "datetime": DateTimeGui,
    }


def _get_default_type_guis():
    global _DEFAULT_TYPE_GUIS
    if _DEFAULT_TYPE_GUIS is None:
        _DEFAULT_TYPE_GUIS = _build_default_type_guis()
    return _DEFAULT_TYPE_GUIS


def __getattr__(name):
    """Lazily build DEFAULT_TYPE_GUIS on first access (see comment above)."""
    if name == "DEFAULT_TYPE_GUIS":
        return _get_default_type_guis()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def suffix_for_ports(port_names):
    """Return the OBJECT_SUFFIXES value matching any of the given port names."""
    for port in port_names:
        if not port or not isinstance(port, str):
            continue
        stripped = port.rstrip("s")
        for key, suffix in OBJECT_SUFFIXES.items():
            if stripped == key.rstrip("s"):
                return suffix
    return None


def strip_shape_annotations(text):
    """Remove "(of/with) shape (...)" segments from a type description.

    Docstrings often annotate array types with their shape, e.g.
    "array, shape (n_samples, n_channels)" or "array-like of shape ``(2,)``".
    Since the dimensions use free-form names (not just digits) and may be
    wrapped in nested/mismatched brackets or rst markup (backticks), a plain
    regex can't reliably match them; a leftover fragment like "n_channels)"
    would otherwise be split off as a bogus type later on. This scans the
    text and drops each such segment using bracket-depth tracking.
    """
    open_brackets = "([{"
    close_brackets = ")]}"
    result = []
    i = 0
    n = len(text)
    while i < n:
        m = re.match(r"(?:of|with)?\s*shape\s*", text[i:], re.IGNORECASE)
        if m:
            j = i + m.end()
            # Skip markup/quote characters surrounding the shape, e.g. ``(...)``
            while j < n and text[j] in "`'\"= ":
                j += 1
            if j < n and text[j] in open_brackets:
                depth = 0
                k = j
                while k < n:
                    if text[k] in open_brackets:
                        depth += 1
                    elif text[k] in close_brackets:
                        depth -= 1
                        if depth == 0:
                            k += 1
                            break
                    k += 1
                while k < n and text[k] in "`'\"":
                    k += 1
                i = k
                continue
        result.append(text[i])
        i += 1
    return "".join(result)


def split_type_hint(annotation):
    """Split a runtime type annotation into type names and a none flag.

    Handles both `X | Y` (`UnionType`) and `typing.Union[X, Y]` annotations,
    as well as plain types. Returns `(type_names, none_select)`.
    """
    if type(annotation) is UnionType or get_origin(annotation) is Union:
        args = get_args(annotation)
        types = [arg.__name__ for arg in args if arg is not NoneType]
        return types or ["str"], NoneType in args
    return [annotation.__name__], annotation is NoneType


def reconcile_default_type(default, types):
    """Align a default value's type with a list of accepted type names.

    Coerces numeric/list/tuple defaults toward an already-accepted type and
    stringifies non-serializable callables; otherwise the default's own type
    name is appended so it stays representable.
    """
    if default is not None and type(default).__name__ not in types:
        if isinstance(default, int) and "float" in types:
            default = float(default)
        elif isinstance(default, float) and "int" in types:
            if default.is_integer():
                default = int(default)
        elif isinstance(default, tuple) and "list" in types:
            default = list(default)
        elif isinstance(default, list) and "tuple" in types:
            default = tuple(default)
        elif isinstance(default, str) and "path" in types:
            pass  # Skip path since path-gui suffices
        else:
            types = [*types, type(default).__name__]
    if callable(default) and not isinstance(default, type):
        default = getattr(default, "__name__", repr(default))
    return default, types


def parse_docstring_type(type_name):
    """Parse a numpydoc-style parameter type description into normalized tokens.

    Returns a dict with:
      - types: list[str] of normalized primitive/container type names
      - options: list[str] literal string choices (also appends "combo" to types)
      - array_dtypes: {container_type: dtype} for numeric array/list types
      - is_dual_tuple: whether the type describes a fixed 2-element tuple
      - none_select: whether "None" is one of the accepted type tokens
      - default: a default value parsed from a "type (default X)" pattern, or
        `inspect.Parameter.empty` if none was found
    """
    if not type_name:
        return {
            "types": [],
            "options": [],
            "array_dtypes": {},
            "is_dual_tuple": False,
            "none_select": False,
            "default": inspect.Parameter.empty,
        }
    is_dual_tuple = bool(
        re.search(r"\btuple\s+of\s+length\s+2\b", type_name, re.IGNORECASE)
    )
    # Filter (<type> of length <length>)
    type_name = re.sub(r"(\w+)\s*of\s*length\s*\d+", r"\1", type_name)
    type_name = strip_shape_annotations(type_name)
    types = type_name.split("|")
    types = [item for sublist in types for item in sublist.split(" or ")]
    types = [item for sublist in types for item in sublist.split(",")]
    types = [t.strip() for t in types]
    # Strip rst inline-code markup, e.g. "``'auto'``" -> "'auto'"
    types = [t.strip("`") for t in types]
    types = [
        ARRAY_TYPE_ALIASES.get(
            t, COLOR_TYPE_ALIASES.get(t, PATH_TYPE_ALIASES.get(t, t))
        )
        for t in types
    ]
    # Remove duplicates while preserving order
    types = list(dict.fromkeys(types))
    # Get instance of <class> and use lower case
    pattern = r"instance of ([\w\.]+)"
    for idx, t in enumerate(types):
        match = re.match(pattern, t)
        if match:
            types[idx] = match.group(1).split(".")[-1]
    # Get containers, e.g. "list of int" -> "list" or "array of int" -> "array"
    default_type_guis = _get_default_type_guis()
    array_dtypes = {}
    pattern = r"(\w+(?:-\w+)*)\s*of\s*(\w+)"
    for idx, t in enumerate(types):
        match = re.match(pattern, t)
        if match:
            container_type = ARRAY_TYPE_ALIASES.get(match.group(1), match.group(1))
            contained_type = match.group(2)
            if (
                container_type in ["list", "tuple"]
                and contained_type in default_type_guis
            ):
                types[idx] = container_type
            elif container_type in ARRAY_CONTAINER_TYPES and (
                contained_type in default_type_guis
                or contained_type in ("int", "float")
            ):
                types[idx] = container_type
                if contained_type in ("int", "float"):
                    array_dtypes[container_type] = contained_type
    # Get "type (default ***)" pattern
    default = inspect.Parameter.empty
    pattern = r"(\w+)\s*\(default\s*([\w'\.]+)\)"
    for idx, t in enumerate(types):
        match = re.match(pattern, t)
        if match:
            types[idx] = match.group(1)
            default_str = match.group(2)
            if default_str.startswith("'") and default_str.endswith("'"):
                default = default_str.strip("'")
            else:
                try:
                    default = literal_eval(default_str)
                except (ValueError, SyntaxError):
                    default = default_str
    # Remove empty strings
    types = [t for t in types if t != ""]
    none_select = "None" in types
    if none_select:
        types.remove("None")

    def _is_quoted(t):
        return (t.startswith("'") and t.endswith("'")) or (
            t.startswith('"') and t.endswith('"')
        )

    options = [t.strip("'\"") for t in types if _is_quoted(t)]
    types = [t for t in types if not _is_quoted(t)]
    if len(options) > 0:
        types.append("combo")
    return {
        "types": types,
        "options": options,
        "array_dtypes": array_dtypes,
        "is_dual_tuple": is_dual_tuple,
        "none_select": none_select,
        "default": default,
    }
