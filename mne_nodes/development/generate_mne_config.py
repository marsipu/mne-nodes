# %%
import importlib

import inspect
from pathlib import Path
from collections import defaultdict
import re
import docstring_parser

from mne_nodes.gui.parameter_widgets import (
    BoolGui,
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
    "slice": DualTupleGui,
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
mnedev_api_path = "C:/Users/martin/Code/mne-python/doc/api"
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
            doc = docstring_parser.parse(inspect.getdoc(obj))
            obj_config = {
                "inputs": {},
                "parameters": {},
                "outputs": {},
                "target": "file",
                "module": complete_module_name,
            }
            # Get inputs and parameters
            parameters = [i for i in doc.meta if "param" in i.args]
            for param in parameters:
                if not param.arg_name[0].isalpha():  # type: ignore
                    continue
                types = param.type_name.split("|")  # type: ignore
                if "None" in types:
                    none_select = True
                    types.remove("None")
                else:
                    none_select = False
                if any([t not in default_type_guis for t in types]):
                    # Add missing types as inputs
                    missing_types.update(types)
                    obj_config["inputs"][param.arg_name] = {  # type: ignore
                        "accepted": param.arg_name,  # type: ignore
                        "optional": none_select,
                    }
                    continue
                param_config = {}
                if len(types) == 0:
                    # If no type is specified, skip
                    continue
                elif len(types) > 1:
                    param_config.update({"types": types, "gui": "MultiTypeGui"})
                else:
                    param_config.update({"gui": default_type_guis[types[0]].__name__})
                param_config.update(
                    {
                        "none_select": none_select,
                        "default": param.default,  # type: ignore
                        "description": param.description,  # type: ignore
                    }
                )
                obj_config["parameters"][param.arg_name] = param_config  # type: ignore
            # Get outputs
            for ret in doc.many_returns:
                return_config = {
                    "accepted": ret.return_name  # type: ignore
                }
                obj_config["outputs"][ret.return_name] = return_config  # type: ignore
            # Add to config
            config["functions"][obj_name] = obj_config

# %%
