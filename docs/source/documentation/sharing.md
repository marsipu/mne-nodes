# Share plugins and pipelines

## Share a plugin

For a plugin created with [function importer](function_importer.md), share the generated project
folder: `pyproject.toml`, README, license, and the source package under `src`.
Include helper modules and non-Python resources and review dependencies.
The recipient can install the project with `python -m pip install .`, or
select its `_config.json` using **Plugins > Load Plugin from Path**.

For a simple legacy path plugin, share the Python file and matching
`_config.json` together, plus its helpers. There is no standalone plugin-export
button: share the files or build a distribution.
See [plugin distribution](plugin_distribution.md) for wheel/source exports and
[plugin format](../development/plugin_format.md) for package structure.

## Save a pipeline

**File > Save Pipeline** stores the graph, selections, parameters, and plugin
metadata. **Save Pipeline As...** writes it to another JSON file.
Neither includes recordings, local settings, nor a standalone installation of
every plugin. On another device, select the BIDS root and restore dependencies.

## Export executable code

The **File** menu exports a Python script, a Jupyter notebook (`.ipynb`), or
a complete-project ZIP. The ZIP contains `pipeline.py`, `pipeline.json`,
`requirements.txt`, and local path-plugin files under `plugins`.
It is not a complete environment or an intentional raw-dataset export.
Local plugin folders are copied recursively, so keep unrelated data and private
files out of them and inspect the archive before sharing.
Exports may also contain local paths and participant identifiers.

Choose **Plain output** for simpler logs, or **Rich output** for formatted
progress and timings.
