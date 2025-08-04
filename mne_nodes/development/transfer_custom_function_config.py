import json

import pandas as pd

from mne_nodes.pipeline.legacy import convert_pandas_meta
from mne_nodes.pipeline.io import TypedJSONEncoder

func_pd = pd.read_csv("../extra/functions.csv", sep=";", index_col=0)
param_pd = pd.read_csv("../extra/parameters.csv", sep=";", index_col=0)
configs = convert_pandas_meta(func_pd, param_pd)

n_jobs_config = {
    "alias": "Number of jobs for multiprocessing",
    "default": -1,
    "unit": None,
    "description": "The number of jobs to run in parallel for selected fucntions. When set to 'auto', the number of available cores is selected. Only for some functions, selecting 'cuda', works",
    "gui": "MultiTypeGui",
    "types": ["int", "combo"],
    "type_kwargs": {
        "IntGui": {"min_val": -1, "special_value_text": "auto"},
        "ComboGui": {"options": ["cuda"]},
    },
}

show_plots_config = {
    "alias": "Show plots",
    "default": True,
    "unit": None,
    "description": "If set to True, the function will show the plot after execution. If set to False, the plot will not be shown.",
    "gui": "BoolGui",
}

enable_cuda_config = {
    "alias": "Enable CUDA",
    "default": False,
    "unit": None,
    "description": "If set to True, the function will use CUDA for processing. If set to False, the function will use CPU.",
    "gui": "BoolGui",
}

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

    # Some modifications
    if module_name == "operations":
        module_dict["parameters"]["n_jobs"] = n_jobs_config
        module_dict["parameters"]["enable_cuda"] = enable_cuda_config
        module_dict["functions"]["filter_data"]["inputs"] = ["raw"]
        module_dict["functions"]["filter_data"]["outputs"] = ["raw"]
        module_dict["functions"]["epoch_raw"]["inputs"] = ["raw", "events"]
    else:
        module_dict["parameters"]["show_plots"] = show_plots_config

    print(print_msg)
    with open(config_file, "w") as f:
        json.dump(module_dict, f, indent=4, cls=TypedJSONEncoder)
    print(success_msg)
