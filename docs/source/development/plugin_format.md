# Plugin structure

## Local files

A path-loaded plugin consists of `my_processing.py` and
`my_processing_config.json` in the same folder. Configuration maps function
names to node metadata. [function importer](../documentation/function_importer.md) generates it.

```json
{
    "example_filter": {
        "inputs": {"raw": {"accepted_ports": ["raw"], "optional": false}},
        "parameters": {
            "highpass": {"gui": "IntGui", "default": 1},
            "lowpass": {"gui": "IntGui", "default": 30}
        },
        "outputs": {"raw": {"accepted_ports": ["raw"]}},
        "target": "file",
        "category": "my_processing",
        "description": "Filter a recording."
    }
}
```

Names must resolve to callables exposed by the plugin. Widget names refer to
classes exported by `mne_nodes.gui.parameter`. Accepted port aliases express
connection compatibility; readers/writers and suffixes describe derivative I/O.
Do not confuse these definitions with a pipeline's saved parameter values.

## Installed packages

Expose configuration from the plugin's importable module, typically
`__init__.py`:

```python
from importlib.resources import files

PLUGIN_NAME = "my_processing"
CONFIG_PATH = files(__package__) / "my_processing_config.json"
SCRIPT_PATH = files(__package__) / "my_processing.py"
```

`CONFIG_PATH` is required. `PLUGIN_NAME` customizes the displayed name;
`SCRIPT_PATH` identifies source containing the configured functions.
Package the JSON and source as resources, and declare dependencies in
`pyproject.toml`. `PLUGIN_GITHUB` can identify the source repository.

For installed discovery, advertise the importable module:

```toml
[project.entry-points."mne_nodes.plugins"]
my_processing = "my_processing"
```

The entry point must load a module, not a function or class.
Test both the installed package and path loading; an editable checkout can
hide missing resources. Refer to [plugins](../documentation/plugins.md) for user actions
and [freesurfer](../documentation/freesurfer.md) for command/FreeSurfer metadata.
