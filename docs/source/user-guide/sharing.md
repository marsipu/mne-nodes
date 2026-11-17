# Share pipelines and plugins

## Share a pipeline

Save or export the pipeline from the **File** menu.

![The File menu with the export entries](../_static/screenshots/linux/file-menu.png)

| Menu entry | Creates | Use it to |
| --- | --- | --- |
| **Save Pipeline** / **Save Pipeline As...** | `.json` | Reopen the pipeline in mne-nodes |
| **Export Python Script...** | `.py` | Run the pipeline without the application |
| **Export Jupyter Notebook...** | `.ipynb` | Run it step by step in a notebook |
| **Export Complete Project...** | `.zip` | Pass on code, `pipeline.json`, `requirements.txt`, and local plugins |

Every export asks whether the script prints plain or rich-formatted progress.
None of these files contain recordings or a Python environment: the recipient
selects the BIDS dataset and installs the plugins.

!!! warning "Check before you share"
    Exports can contain local paths and participant identifiers. The ZIP copies
    local plugin folders completely, so keep private files out of them.

## Share a plugin

A plugin created with the [function importer](function_importer.md) is an
ordinary Python project. Share it in one of these ways:

| Share | The recipient |
| --- | --- |
| The project folder | Runs `python -m pip install .` in it, or loads its `_config.json` with **Load Plugin from Path** |
| A wheel from `dist/` | Runs `python -m pip install <wheel-file>` |
| A GitHub repository | Enters its URL in **Load Plugin from GitHub** |

Build the wheel in the project folder:

```console
python -m pip install build twine
python -m build
python -m twine check dist/*
```

Before a release, check the name, version, license, and dependencies in
`pyproject.toml`, and test an installation of the built wheel. Tools such as
FreeSurfer are not installed by pip and need their own instructions.

mne-nodes never uploads anything. Publishing to GitHub or PyPI is your own
step with your own tools.
