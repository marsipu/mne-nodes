# %%
import mne
import inspect
from pathlib import Path

mne_version = "1.12"

# %%
categories = {
    "datasets": "datasets",
    "visualization": "viz",
    "preprocessing": ["channels", "preprocessing", "filter", "chpi", "transforms"],
}
# Get all functions from mne module
all_functions = {
    name: obj for name, obj in inspect.getmembers(mne) if inspect.isfunction(obj)
}
viz_functions = {
    name: obj for name, obj in inspect.getmembers(mne.viz) if inspect.isfunction(obj)
}

# %%
# Group functions by API category
mnedev_api_path = "C:/Users/marti/Code/mne-python/doc/api"
api_categories = [f.stem for f in Path(mnedev_api_path).glob("*.rst")]

# Create a mapping of functions to their API categories
functions_sorted = {}

for category in api_categories:
    functions_sorted[category] = []
    rst_file = Path(mnedev_api_path) / f"{category}.rst"
    if rst_file.exists():
        with open(rst_file, encoding="utf-8") as f:
            content = f.read()

        # Check each function to see if it appears in this category's rst file
        for func_name, func_obj in all_functions.items():
            if func_name in content:
                functions_sorted[category].append(func_name)
