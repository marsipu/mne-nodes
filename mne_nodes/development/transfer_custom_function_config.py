import json

import pandas as pd

from mne_nodes.pipeline.io import TypedJSONEncoder
from mne_nodes.pipeline.legacy import convert_pandas_meta

func_pd = pd.read_csv("../extra/functions.csv", sep=";", index_col=0)
param_pd = pd.read_csv("../extra/parameters.csv", sep=";", index_col=0)
configs = convert_pandas_meta(func_pd, param_pd)

for module_name, module_dict in configs.items():
    if module_name == "operations":
        module_type = "basic_operations"
        config_file = "../basic_operations/basic_operations_config.json"
        print_msg = f"Found {len(module_dict['functions'])} operations functions."
        success_msg = "Operation configuration files created successfully."
    else:
        module_type = "basic_plot"
        config_file = "../basic_plot/basic_plot_config.json"
        print_msg = f"Found {len(module_dict['functions'])} plotting functions."
        success_msg = "Function configuration files created successfully."

    for func_dict in module_dict["functions"].values():
        func_dict["module"] = module_type
    module_dict["module_name"] = module_type
    module_dict["module_alias"] = module_type

    print(print_msg)
    with open(config_file, "w") as f:
        json.dump(module_dict, f, indent=4, cls=TypedJSONEncoder)
        # Add empty line at the end of the file
        f.write("\n")
    print(success_msg)
