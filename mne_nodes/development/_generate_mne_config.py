# %%
import importlib
import inspect
import io
import json
import re
import sys
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path

import docstring_parser
from docutils.core import publish_parts
from tqdm import tqdm

from mne_nodes.gui.parameter import DualTupleGui
from mne_nodes.pipeline.function_parser import DEFAULT_TYPE_GUIS as default_type_guis
from mne_nodes.pipeline.function_parser import TYPE_DEFAULTS as type_defaults
from mne_nodes.pipeline.function_parser import (
    parse_docstring_type,
    reconcile_default_type,
    strip_shape_annotations,
)
from mne_nodes.pipeline.function_parser import suffix_for_ports as _suffix_for_ports
from mne_nodes.pipeline.io import TypedJSONEncoder

# This script generates the config/scraper output for both the mne_functions
# and mne_io_functions plugins, which live in their own sibling repositories
# checked out next to this one (mne-nodes).
REPOS_DIR = Path(__file__).resolve().parents[3]
MNE_FUNCTIONS_PKG = REPOS_DIR / "mne-nodes_mne-functions" / "mne_nodes_mne_functions"
MNE_IO_FUNCTIONS_PKG = (
    REPOS_DIR / "mne-nodes_mne-io-functions" / "mne_nodes_mne_io_functions"
)

group_functions = {"mne.grand_average"}

# Populated from _collect_object_aliases() once `objects` has been built below.
class_alias = {}

exclude_categories = [
    "connectivity",
    "creating_from_arrays",
    "logging",
    "misc",
    "python_reference",
    "realtime",
    "file_io",
    "reading_raw_data",
]


def _rst_to_qt_rich_text(text):
    """Convert an MNE docstring fragment from RST to Qt-compatible HTML."""
    if not text:
        return text
    parts = publish_parts(
        text,
        writer_name="html5",
        settings_overrides={
            "halt_level": 6,
            "report_level": 5,
            "warning_stream": io.StringIO(),
        },
    )
    return _docutils_html_to_qt_html(parts["html_body"])


class _DocutilsHTMLToQtHTML(HTMLParser):
    """Translate docutils CSS classes into markup supported by Qt rich text."""

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.output = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set(attrs.pop("class", "").split())
        if tag == "main":
            return
        if "literal" in classes:
            self.output.append('<span style="font-family: monospace;">')
        elif "literal-block" in classes:
            self.output.append("<pre>")
        elif tag in {"html", "head", "body"}:
            return
        else:
            self.output.append("<" + tag)
            for name, value in attrs.items():
                if value is not None:
                    escaped = value.replace("&", "&amp;").replace('"', "&quot;")
                    self.output.append(f' {name}="{escaped}"')
            self.output.append(">")

    def handle_endtag(self, tag):
        if tag == "main":
            return
        if tag in {"html", "head", "body"}:
            return
        if tag == "span":
            self.output.append("</span>")
        elif tag == "pre":
            self.output.append("</pre>")
        else:
            self.output.append(f"</{tag}>")

    def handle_data(self, data):
        self.output.append(data)

    def handle_entityref(self, name):
        self.output.append(f"&{name};")

    def handle_charref(self, name):
        self.output.append(f"&#{name};")


def _docutils_html_to_qt_html(html):
    parser = _DocutilsHTMLToQtHTML()
    parser.feed(html)
    parser.close()
    return "".join(parser.output).strip()


def _accepted_aliases(name):
    """Return accepted port names for a class or output name."""
    key = name.lower()
    return _accepted_names(key, *class_alias.get(key, []))


def _accepted_names_from_types(types):
    accepted = []
    for type_name in types:
        accepted_type = type_name.split(" of ", 1)[-1].strip()
        accepted_type = accepted_type.rsplit(".", 1)[-1]
        for name in _accepted_aliases(accepted_type):
            if name not in accepted:
                accepted.append(name)
    return accepted


def _accepted_names_from_type_name(type_name):
    if not type_name:
        return []
    types = re.split(r"\s*\|\s*|\s+or\s+|,", type_name)
    return _accepted_names_from_types([type.strip() for type in types])


def _accepted_names(*names):
    accepted = []
    for name in names:
        if name and name not in accepted:
            accepted.append(name)
    return accepted


def _extract_type_tokens(type_name):
    """Split a docstring type string into raw class-name tokens.

    Only capitalized tokens (e.g. "Covariance", the X in "instance of X") are
    kept, since real mne classes are capitalized while primitive type
    keywords (int, str, array, ...) are not; this keeps the auto-derived
    aliases below from being polluted by generic type names. Tokens must also
    look like a single identifier, so junk like "None (default None)" (left
    over from stripping a "<type> (default ...)" annotation) is rejected
    instead of being kept as a bogus "class".
    """
    if not type_name:
        return []
    text = strip_shape_annotations(type_name)
    text = re.sub(r"(\w+)\s*of\s*length\s*\d+", r"\1", text)
    tokens = []
    for part in re.split(r"\s*\|\s*|\s+or\s+|,", text):
        part = part.strip().strip("`")
        match = re.match(r"instance of ([\w\.]+)", part)
        if match:
            part = match.group(1)
        else:
            part = part.split(" of ", 1)[-1].strip()
            default_match = re.match(r"^(\w+)\s*\(default", part)
            if default_match:
                part = default_match.group(1)
        part = part.rsplit(".", 1)[-1]
        if re.fullmatch(r"[A-Za-z_]\w*", part) and part[0].isupper() and part != "None":
            tokens.append(part)
    return tokens


def _collect_object_aliases(objects):
    """Derive object port aliases from how parameters are actually named.

    For every documented parameter whose type resolves to a class name (e.g.
    "instance of Covariance"), the parameter's own arg_name is recorded as an
    alias of that class (e.g. Covariance -> {"cov", "noise_cov"}), instead of
    hand-maintaining a table that easily gets out of sync (and is compared
    case-sensitively) with the actual class names.
    """
    aliases = defaultdict(set)
    for module_dict in objects.values():
        for plugin_name, obj_list in module_dict.items():
            for obj_item in obj_list:
                sub_modules = obj_item.split(".")[:-1]
                obj_name = obj_item.split(".")[-1]
                module_name = ".".join([plugin_name] + sub_modules)
                try:
                    module = importlib.import_module(module_name)
                    obj = getattr(module, obj_name)
                except (ImportError, AttributeError):
                    continue
                if inspect.isclass(obj):
                    aliases.setdefault(obj_name.lower(), set())
                elif not inspect.isfunction(obj):
                    continue
                docstring = inspect.getdoc(obj)
                if not docstring:
                    continue
                doc = docstring_parser.parse(docstring)
                for meta_param in doc.meta:
                    if "param" not in meta_param.args:
                        continue
                    for arg_name in meta_param.arg_name.split(","):
                        arg_name = arg_name.strip().lower()
                        if not arg_name or not arg_name[0].isalpha():
                            continue
                        for token in _extract_type_tokens(meta_param.type_name):
                            key = token.lower()
                            if key and arg_name != key:
                                aliases[key].add(arg_name)
    return {key: sorted(names) for key, names in aliases.items()}


# %%
def parse_rst_functions(path):
    text = Path(path).read_text()

    module_pattern = re.compile(r"\.\.\s*currentmodule::\s*([\w\.]+)")
    auto_module_pattern = re.compile(r"\.\.\s*automodule::\s*([\w\.]+)")

    module = None
    functions = defaultdict(list)

    for line in text.splitlines():
        # Detect module
        m = module_pattern.match(line.strip())
        if m:
            module = m.group(1)
            continue

        m = auto_module_pattern.match(line.strip())
        if m:
            module = m.group(1)
            continue

        # Detect items
        if line.startswith("   "):  # indented entries 3 spaces
            name = line.strip()
            if not name[0].isalpha():
                continue
            functions[module].append(name)

    return dict(functions)


# Group functions by API category
mnedev_api_path = REPOS_DIR / "mne-python/doc/api"
if not mnedev_api_path.exists():
    print(f"{mnedev_api_path} does not exist!")
    sys.exit(1)
api_categories = {
    f.stem: f
    for f in Path(mnedev_api_path).glob("*.rst")
    if f.stem not in exclude_categories
}

objects = {}
for category, category_path in api_categories.items():
    objects[category] = parse_rst_functions(category_path)

class_alias = _collect_object_aliases(objects)


def _is_class_alias(name):
    """Whether name (case-insensitive) refers to a recognized class/alias."""
    key = name.lower()
    if key in class_alias:
        return True
    return any(key in aliases for aliases in class_alias.values())


def _is_known_io_name(name):
    """Whether name matches a file_io read/write function's object alias."""
    key = name.lower()
    return any(key in entry["aliases"] for entry in io_read_entries + io_write_entries)


def _s_variants(name):
    """Return name plus its singular/plural counterpart (e.g. "surf"/"surfs")."""
    if name.endswith("s"):
        return (name, name[:-1])
    return (name, name + "s")


def _expand_alias_variants(names):
    """Expand a list of alias names with their singular/plural counterparts."""
    expanded = []
    for name in names:
        for variant in _s_variants(name):
            if variant not in expanded:
                expanded.append(variant)
    return expanded


# %% Extract read/write functions from every api rst file (not just file_io.rst,
# since domain-specific I/O functions like mne.time_frequency.write_tfrs live
# in their own category file). Only functions taking a single fname/filename
# argument plus (for writers) a single object argument are considered;
# anything more ambiguous is skipped.
io_read_entries = []
io_write_entries = []
_seen_io_functions = set()
for rst_path in sorted(Path(mnedev_api_path).glob("*.rst")):
    for plugin_name, obj_list in parse_rst_functions(rst_path).items():
        for obj_item in obj_list:
            obj_name = obj_item.split(".")[-1]
            if not (obj_name.startswith(("read_", "write_"))):
                continue
            # Raw file importers (read_raw_fif, read_raw_edf, ...) are handled
            # by the pipeline's dedicated raw-data import, not as generic I/O.
            if obj_name.startswith("read_raw"):
                continue
            sub_modules = obj_item.split(".")[:-1]
            module_name = ".".join([plugin_name] + sub_modules)
            if (obj_name, module_name) in _seen_io_functions:
                continue
            _seen_io_functions.add((obj_name, module_name))
            try:
                module = importlib.import_module(module_name)
                obj = getattr(module, obj_name)
            except (ImportError, AttributeError):
                continue
            if not inspect.isfunction(obj):
                continue
            docstring = inspect.getdoc(obj)
            if not docstring:
                continue
            doc = docstring_parser.parse(docstring)
            try:
                sig = inspect.signature(obj)
            except ValueError:
                continue
            fname_param = next(
                (
                    p
                    for p in sig.parameters
                    if "fname" in p.lower() or p.lower() == "filename"
                ),
                None,
            )
            if fname_param is None:
                continue
            var_kinds = (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            )
            required = [
                p
                for p, v in sig.parameters.items()
                if v.default is inspect.Parameter.empty and v.kind not in var_kinds
            ]
            if fname_param not in required:
                continue
            if obj_name.startswith("read_"):
                # Only accept functions with a single required (fname) param.
                # Some functions (e.g. read_events) conditionally return extra
                # values (via a kwarg like return_event_id); use the first
                # documented return as the primary object.
                if len(required) != 1 or not doc.many_returns:
                    continue
                return_name = doc.many_returns[0].return_name
                if not return_name or "," in return_name:
                    continue
                primary_names = _expand_alias_variants([return_name])
                aliases = _expand_alias_variants(
                    _accepted_names(
                        return_name,
                        *_accepted_aliases(return_name),
                        *_accepted_names_from_type_name(doc.many_returns[0].type_name),
                    )
                )
                io_read_entries.append(
                    {
                        "function": obj_name,
                        "primary_names": primary_names,
                        "aliases": aliases,
                        "obj": obj,
                        "module_name": module_name,
                    }
                )
            else:
                # Only accept functions taking exactly one object besides fname.
                if len(required) != 2:
                    continue
                object_param = next(p for p in required if p != fname_param)
                primary_names = _expand_alias_variants([object_param])
                aliases = _expand_alias_variants(
                    _accepted_names(object_param, *_accepted_aliases(object_param))
                )
                io_write_entries.append(
                    {
                        "function": obj_name,
                        "primary_names": primary_names,
                        "aliases": aliases,
                        "obj": obj,
                        "module_name": module_name,
                    }
                )


def get_param_config(param, sig, obj_config):
    # Skip parameters that don't have a valid name (e.g. *args, **kwargs)
    if not param.arg_name[0].isalpha():  # type: ignore
        return
    # Get default from inspection signature
    default = sig.parameters[param.arg_name].default  # type: ignore
    parsed = parse_docstring_type(param.type_name)  # type: ignore
    types = parsed["types"]
    options = parsed["options"]
    array_dtypes = parsed["array_dtypes"]
    is_dual_tuple = parsed["is_dual_tuple"]
    # Only use the type description's default if the signature had none.
    if (
        default is inspect.Parameter.empty
        and parsed["default"] is not inspect.Parameter.empty
    ):
        default = parsed["default"]
    none_select = parsed["none_select"] or default is None
    # Non-primitive types (object references) are treated as node inputs.
    non_primitive = [t for t in types if t not in default_type_guis]
    # A name matching a known class/io alias only forces a param into being an
    # input when its type isn't already a clean, GUI-backed primitive (e.g.
    # "DataFrame") or is a container commonly used for pipeline data (e.g.
    # array-typed "events"); this avoids sweeping in unrelated params that
    # merely share a name with an alias (e.g. Epochs' "proj" bool vs.
    # Projection's "proj"/"projs", or "metadata" vs. the DataFrame class).
    container_types = ("array", "dict", "list", "tuple")
    force_input = False
    if not types or non_primitive or any(t in container_types for t in types):
        force_input = _is_class_alias(param.arg_name) or _is_known_io_name(
            param.arg_name
        )
    if force_input or len(types) == 0 or len(non_primitive) > 0:
        # Report only genuinely unrecognized types, not known object classes.
        for t in non_primitive:
            if not _is_class_alias(t):
                missing_types[t].add(param.arg_name)  # type: ignore
        input_config = {  # type: ignore
            "accepted_ports": _accepted_names(
                param.arg_name, *_accepted_names_from_types(types)
            ),
            "optional": default is not inspect.Parameter.empty,
        }
        obj_config["inputs"][param.arg_name] = input_config  # type: ignore
        return
    # get rid of empty default
    if default is inspect.Parameter.empty:
        default = type_defaults.get(types[0], None)
        none_select = default is None or none_select
    default, types = reconcile_default_type(default, types)
    # If types is "str" and "combo", then remove "str" and keep "combo"
    if len(types) == 2 and "str" in types and "combo" in types:
        types.remove("str")
    # Regular parameters with known types
    param_config = {}
    if len(types) > 1:
        param_config.update({"types": types, "gui": "MultiTypeGui"})
        type_kwargs = {}
        if len(options) > 0:
            type_kwargs["combo"] = {"options": options}
        for arr_type, dtype in array_dtypes.items():
            if arr_type in types:
                type_kwargs[arr_type] = {"dtype": dtype}
        if type_kwargs:
            param_config["type_kwargs"] = type_kwargs
    else:
        gui_class = default_type_guis[types[0]]
        if types[0] == "tuple" and is_dual_tuple:
            gui_class = DualTupleGui
        param_config.update({"gui": gui_class.__name__})
        if len(options) > 0:
            param_config["options"] = options
        if types[0] in array_dtypes:
            param_config["dtype"] = array_dtypes[types[0]]

    param_config.update(
        {
            "default": default,
            "none_select": none_select,
            "description": _rst_to_qt_rich_text(param.description),  # type: ignore
        }
    )
    obj_config["parameters"][param.arg_name] = param_config  # type: ignore


def should_skip_object(doc):
    skip_phrases = [
        "Direct class instantiation is discouraged",
        "This class should usually not be instantiated directly",
        "This class should not be instantiated directly",
        "This class is generally not meant to be instantiated directly",
        "Direct class instantiation is not supported",
        "should be instantiated with",
    ]
    return any(d in str(doc.description) for d in skip_phrases)


def build_object_config(obj, *, module_name, category, sub_category, class_name=None):
    docstring = inspect.getdoc(obj)
    if not docstring:
        return None
    doc = docstring_parser.parse(docstring)
    obj_config = {
        "inputs": {},
        "parameters": {},
        "outputs": {},
        "target": (
            "group" if f"{module_name}.{obj.__name__}" in group_functions else "file"
        ),
        "category": category,
        "sub_category": sub_category,
        "description": _rst_to_qt_rich_text(
            doc.long_description if doc.long_description else doc.short_description
        ),
        "module_name": module_name,
        "class_name": class_name,
    }
    try:
        sig = inspect.signature(obj)
    except ValueError:
        print(f"Could not get signature for {module_name}. Skipping.")
        return None
    parameters = [i for i in doc.meta if "param" in i.args]
    # add lower class-name as input if class_name is not None
    if class_name is not None:
        lower_name = class_name.lower()
        input_config = {
            "accepted_ports": _accepted_names(
                lower_name, *_accepted_aliases(lower_name)
            ),
            "optional": False,
        }
        obj_config["inputs"][lower_name] = input_config
        # change sub-category
        obj_config["sub_category"] = (
            f"{sub_category}.{lower_name}" if sub_category else lower_name
        )
    for param in parameters:
        if "," in param.arg_name:  # type: ignore
            # If multiple parameters are described in one line, split them.
            param_names = [name.strip() for name in param.arg_name.split(",")]  # type: ignore
            for name in param_names:
                param_copy = docstring_parser.DocstringParam(
                    args=param.args,
                    is_optional=param.is_optional,  # type: ignore
                    default=param.default,  # type: ignore
                    arg_name=name,
                    type_name=param.type_name,  # type: ignore
                    description=param.description,
                )
                if name not in sig.parameters:
                    continue
                get_param_config(param_copy, sig, obj_config)
        else:
            if param.arg_name not in sig.parameters:  # type: ignore
                continue
            get_param_config(param, sig, obj_config)

    if inspect.isclass(obj):
        output_key = obj.__name__.lower()
        accepted = _accepted_aliases(output_key)
        output_key = accepted[0]
        return_config = {"accepted_ports": accepted}  # type: ignore
        obj_config["outputs"][output_key] = return_config  # type: ignore
    else:
        for ret in doc.many_returns:
            # Set output name to class name if it is an instance of the class for methods
            if ret.return_name is None:
                continue
            if class_name is not None and any(
                x in ret.return_name.lower() for x in ["inst", "instance", "self"]
            ):
                output_name = class_name.lower()
            else:
                output_name = ret.return_name
            accepted = _accepted_names(
                output_name,
                *_accepted_aliases(output_name),
                *_accepted_names_from_type_name(ret.type_name),
            )
            return_config = {"accepted_ports": accepted}  # type: ignore
            obj_config["outputs"][output_name] = return_config  # type: ignore
    return doc, obj_config


def iter_public_class_methods(cls):
    seen = set()
    for owner_cls in cls.__mro__:
        if owner_cls is object:
            continue
        # Only include methods declared on classes that belong to mne.
        if not owner_cls.__module__.startswith("mne"):
            continue
        for method_name, method_obj in owner_cls.__dict__.items():
            if method_name.startswith("_") or method_name in seen:
                continue
            if isinstance(method_obj, (staticmethod, classmethod)):
                method_obj = method_obj.__func__
            if inspect.isfunction(method_obj):
                seen.add(method_name)
                yield method_name, method_obj


# %% Generate config
config = {}
missing_types = defaultdict(set)

for category, module_dict in objects.items():
    for plugin_name, obj_list in module_dict.items():
        m_split = plugin_name.split(".")
        if len(m_split) == 1 or m_split[-1] == category:
            sub_category = None
        else:
            sub_category = m_split[-1]
        for obj_item in tqdm(obj_list):
            sub_modules = obj_item.split(".")[:-1]
            obj_name = obj_item.split(".")[-1]
            module_name = ".".join([plugin_name] + sub_modules)
            module = importlib.import_module(module_name)
            obj = getattr(module, obj_name)
            if not inspect.isfunction(obj) and not inspect.isclass(obj):
                print(
                    f"Skipping {obj_item} in module {module_name} because it's not a function or class."
                )
                continue
            if obj_name == "write_events":
                pass
            obj_config_result = build_object_config(
                obj,
                module_name=module_name,
                category=category,
                sub_category=sub_category,
            )
            if obj_config_result is None:
                continue
            doc, obj_config = obj_config_result
            if should_skip_object(doc):
                print(
                    f"Skipping {obj_item} because direct instantiation is discouraged."
                )
            else:
                config[obj_name] = obj_config

            if inspect.isclass(obj):
                for method_name, method_obj in iter_public_class_methods(obj):
                    method_path = f"{obj_name}.{method_name}"
                    method_config_result = build_object_config(
                        method_obj,
                        module_name=module_name,
                        category=category,
                        sub_category=sub_category,
                        class_name=obj_name,
                    )
                    if method_config_result is None:
                        continue
                    _, method_config = method_config_result
                    config[method_path] = method_config

# Fallback for objects with no free write_* function (e.g. Epochs, saved via
# Epochs.save()): map each class's accepted port names to its "<Class>.save" entry.
save_method_lookup = {}
for key, cfg in config.items():
    if key.endswith(".save") and cfg.get("class_name"):
        for alias in _accepted_names(
            cfg["class_name"].lower(), *_accepted_aliases(cfg["class_name"].lower())
        ):
            save_method_lookup.setdefault(alias, key)

# Ensure every referenced file_io read/write function has its own config entry
# (a node like any other function), reusing it if already present via its
# domain category (e.g. read_cov/write_cov already exist under "covariance").
for entry in io_read_entries + io_write_entries:
    obj_name = entry["function"]
    if obj_name in config:
        continue
    io_config_result = build_object_config(
        entry["obj"],
        module_name=entry["module_name"],
        category="file_io",
        sub_category=None,
    )
    if io_config_result is None:
        continue
    io_doc, io_obj_config = io_config_result
    if should_skip_object(io_doc):
        continue
    config[obj_name] = io_obj_config


def _find_io_entry(port, entries):
    """Find io entry matching port name by primary name first, then by aliases."""
    return next(
        (e for e in entries if port in e.get("primary_names", [])),
        next((e for e in entries if port in e["aliases"]), None),
    )


# Annotate inputs/outputs with a reference to the matching file_io read/write
# function, if any. The function itself (and its parameters) lives in its own
# config entry above, so only the name is stored here to avoid duplication.
for obj_config in config.values():
    for input_cfg in obj_config["inputs"].values():
        read_map = {}
        suffix_map = {}
        for port in input_cfg.get("accepted_ports", []):
            entry = _find_io_entry(port, io_read_entries)
            if entry is not None:
                read_map[port] = entry["function"]
                suffix = _suffix_for_ports([port]) or _suffix_for_ports(
                    entry.get("primary_names", [])
                )
                if suffix:
                    suffix_map[port] = suffix
        if read_map:
            input_cfg["read"] = read_map
        if suffix_map:
            input_cfg["suffix"] = suffix_map

    for output_cfg in obj_config["outputs"].values():
        write_map = {}
        suffix_map = {}
        for port in output_cfg.get("accepted_ports", []):
            entry = _find_io_entry(port, io_write_entries)
            if entry is not None:
                write_map[port] = entry["function"]
                suffix = _suffix_for_ports([port]) or _suffix_for_ports(
                    entry.get("primary_names", [])
                )
                if suffix:
                    suffix_map[port] = suffix
            elif port in save_method_lookup:
                write_map[port] = save_method_lookup[port]
                suffix = _suffix_for_ports([port])
                if suffix:
                    suffix_map[port] = suffix
        if write_map:
            output_cfg["write"] = write_map
        if suffix_map:
            output_cfg["suffix"] = suffix_map

# Split out I/O read/write functions into their own config file, since they
# are referenced by name from other nodes' inputs/outputs "read"/"write" maps
# rather than needing to be duplicated inline. This also includes "<Class>.save"
# methods used as the write fallback for classes without a free write_* function.
io_function_names = {entry["function"] for entry in io_read_entries + io_write_entries}
io_function_names.update(save_method_lookup.values())
io_config = {
    name: config.pop(name) for name in list(config) if name in io_function_names
}

# Save config (mne_functions plugin)
config_path = MNE_FUNCTIONS_PKG / "mne_functions_config.json"
with open(config_path, "w") as file:
    json.dump(config, file, indent=4, cls=TypedJSONEncoder)

# Save I/O functions config (mne_io_functions plugin)
io_config_path = MNE_IO_FUNCTIONS_PKG / "mne_io_functions_config.json"
with open(io_config_path, "w") as file:
    json.dump(io_config, file, indent=4, cls=TypedJSONEncoder)

# Save the auto-derived object aliases for inspection (to spot-check
# associations and find classes that might still be missing aliases).
aliases_path = MNE_FUNCTIONS_PKG / "object_aliases.json"
with open(aliases_path, "w") as file:
    json.dump(dict(sorted(class_alias.items())), file, indent=4, cls=TypedJSONEncoder)

# Sort dictionary keys on length of their lists
missing_types = dict(
    sorted(missing_types.items(), key=lambda item: len(item[1]), reverse=True)
)

# Save missing types
missing_path = MNE_FUNCTIONS_PKG / "missing_types.json"
with open(missing_path, "w") as file:
    json.dump(missing_types, file, indent=4, cls=TypedJSONEncoder)
print(f"Scraped {len(config)} functions/classes from mne")
print(f"Config saved to {config_path}")
print(f"I/O functions config saved to {io_config_path} ({len(io_config)} entries)")
print(f"Aliases saved to {aliases_path}")
print(f"Missing types saved to {missing_path}")
