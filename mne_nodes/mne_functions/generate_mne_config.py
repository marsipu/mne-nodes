# %%
from ast import literal_eval
import importlib

import inspect
import json
from pathlib import Path
from collections import defaultdict
from pprint import pprint
import re
import docstring_parser

from mne_nodes.gui.parameter_widgets import (
    BoolGui,
    ComboGui,
    DictGui,
    DualTupleGui,
    FloatGui,
    IntGui,
    ListGui,
    StringGui,
)

default_type_guis = {
    "int": IntGui,
    "float": FloatGui,
    "str": StringGui,
    "bool": BoolGui,
    "list": ListGui,
    "dict": DictGui,
    "tuple": DualTupleGui,
    "combo": ComboGui,
}


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
mnedev_api_path = Path(__file__).resolve().parents[3] / "mne-python/doc/api"
exclude_categories = [
    "connectivity",
    "creating_from_arrays",
    "logging",
    "misc",
    "python_reference",
    "realtime",
]
api_categories = {
    f.stem: f
    for f in Path(mnedev_api_path).glob("*.rst")
    if f.stem not in exclude_categories
}

objects = {}
for category, category_path in api_categories.items():
    objects[category] = parse_rst_functions(category_path)


def get_param_config(param, sig, obj_config):
    # Skip parameters that don't have a valid name (e.g. *args, **kwargs)
    if not param.arg_name[0].isalpha():  # type: ignore
        return
    types = param.type_name.split("|")  # type: ignore
    # split or
    types = [item for sublist in types for item in sublist.split(" or ")]
    # split ,
    types = [item for sublist in types for item in sublist.split(",")]
    # Remove spaces
    types = [t.strip() for t in types]
    # Filter (default ***)
    pattern = r"(\w+)\s\(default ([\w']+)\)"
    types = [re.sub(pattern, r"\1", t) for t in types]
    # Get containters
    pattern = r"(\w+)\s*of\s*(\w+)"
    for idx, t in enumerate(types):
        match = re.match(pattern, t)
        if match:
            container_type = match.group(1)
            contained_type = match.group(2)
            if (
                container_type in ["list", "tuple"]
                and contained_type in default_type_guis
            ):
                types[idx] = container_type
    # Get default from inspection signature
    default = sig.parameters[param.arg_name].default  # type: ignore
    # Get "type (default ***)" pattern
    pattern = r"(\w+)\s*\(default\s*([\w'\.]+)\)"
    for idx, t in enumerate(types):
        match = re.match(pattern, t)
        if match:
            tp = match.group(1)
            types[idx] = tp
            # Only try getting default from string if not gotten from signature
            if default is inspect.Parameter.empty:
                default_str = match.group(2)
                if default_str.startswith("'") and default_str.endswith("'"):
                    default = default_str.strip("'")
                else:
                    try:
                        default = literal_eval(default_str)
                    except (ValueError, SyntaxError):
                        default = default_str
    # # Remove parentheses
    # types = [t.replace("(", "").replace(")", "") for t in types]
    if "None" in types:
        none_select = True
        types.remove("None")
    else:
        none_select = False
    # Get string options and remove them from types
    options = [t.strip("'") for t in types if t.startswith("'") and t.endswith("'")]
    types = [t for t in types if t.strip("'") not in options]
    if len(options) > 0:
        types.append("combo")
    # Missing types
    missing = [t for t in types if t not in default_type_guis]
    if len(types) == 0 or len(missing) > 0 or default is inspect.Parameter.empty:
        # Add params with missing types or no Default as inputs
        missing_types.update(missing)
        input_config = {  # type: ignore
            "accepted": param.arg_name,  # type: ignore
            "optional": none_select,
            "types": types,
        }
        obj_config["inputs"][param.arg_name] = input_config  # type: ignore
        return
    # Regular parameters with known types
    param_config = {}
    if len(types) > 1:
        param_config.update({"types": types, "gui": "MultiTypeGui"})
        if len(options) > 0:
            param_config["type_kwargs"] = {"combo": {"options": options}}
    else:
        param_config.update({"gui": default_type_guis[types[0]].__name__})
        if len(options) > 0:
            param_config["options"] = options
    param_config.update(
        {
            "default": default,
            "none_select": none_select,
            "description": param.description,  # type: ignore
        }
    )
    obj_config["parameters"][param.arg_name] = param_config  # type: ignore


# %%
config = {"module": {}, "functions": {}, "categories": {}}
missing_types = set()
for category, module_dict in objects.items():
    for module_name, obj_list in module_dict.items():
        m_split = module_name.split(".")
        if len(m_split) == 1 or m_split[-1] == category:
            sub_category = None
        else:
            sub_category = m_split[-1]
        for obj_item in obj_list:
            sub_modules = obj_item.split(".")[:-1]
            obj_name = obj_item.split(".")[-1]
            complete_module_name = ".".join([module_name] + sub_modules)
            module = importlib.import_module(complete_module_name)
            obj = getattr(module, obj_name)
            if not inspect.isfunction(obj) and not inspect.isclass(obj):
                print(
                    f"Skipping {obj_item} in module {complete_module_name} because it's not a function or class."
                )
                continue
            doc = docstring_parser.parse(inspect.getdoc(obj))
            # Skip if descriptions does not recommend direct instantiation
            if any(
                [
                    d in str(doc.description)
                    for d in [
                        "Direct class instantiation is discouraged",
                        "This class should usually not be instantiated directly",
                        "This class should not be instantiated directly",
                        "This class is generally not meant to be instantiated directly",
                        "Direct class instantiation is not supported",
                        "should be instantiated with",
                    ]
                ]
            ):
                print(
                    f"Skipping {obj_item} because direct instantiation is discouraged."
                )
                continue
            obj_config = {
                "inputs": {},
                "parameters": {},
                "outputs": {},
                "target": "file",
                "category": category,
                "sub_category": sub_category,
                "description": doc.long_description
                if doc.long_description
                else doc.short_description,
                "module": complete_module_name,
            }
            # Get function signature for defaults
            try:
                sig = inspect.signature(obj)
            except ValueError:
                print(
                    f"Could not get signature for {obj_item} in module {complete_module_name}. Skipping."
                )
                continue
            # Get inputs and parameters
            parameters = [i for i in doc.meta if "param" in i.args]
            for param in parameters:
                if "," in param.arg_name:  # type: ignore
                    # If multiple parameters are described in one line, split them
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
                        get_param_config(param_copy, sig, obj_config)
                else:
                    get_param_config(param, sig, obj_config)
            # Get outputs
            for ret in doc.many_returns:
                return_config = {
                    "accepted": ret.return_name  # type: ignore
                }
                obj_config["outputs"][ret.return_name] = return_config  # type: ignore
            # Add to config
            config["functions"][obj_name] = obj_config

# Save config
config_path = Path(__file__).parent / "mne_functions_config.json"
with open(config_path, "w") as file:
    json.dump(config, file, indent=4)
print("Missing types:")
pprint(missing_types)
print(f"Scraped {len(config['functions'])} functions/classes from mne")
print(f"Config saved to {config_path}")
