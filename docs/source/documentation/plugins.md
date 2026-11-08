# Load and manage plugins

Plugins provide Python functions and the configuration that describes their
ports, parameters, and categories. Installing mne-nodes alone does not give you
every analysis function.

## Load from a path

Choose **Plugins > Load Plugin from Path** and select the JSON configuration.
The two files must be in the same folder with matching names:

```text
my_processing.py
my_processing_config.json
```

The plugin name must be a valid Python module name. Generate these files with
[function importer](function_importer.md), or use files supplied by a plugin author.
Dependencies must be available in the application's Python environment.
Generated packages keep the pair inside
`src/mne_nodes_my_processing/`. When a project is detected, the load dialog
offers optional installation; leave it unchecked to load from source directly.

## Load an installed package or GitHub plugin

* **Load Plugin from Module:** enter the importable Python module name, not a
  file path. The package must expose its plugin configuration; see
  [plugin format](../development/plugin_format.md).
* **Load Plugin from GitHub:** enter the repository URL of an installable
  plugin package. Review any installation prompt before proceeding.
* Installed packages can advertise plugins through `mne_nodes.plugins`
  entry points. Newly discovered installed plugins are enabled automatically;
  plugins you disable stay disabled. Use **Manage Plugins > Refresh** to rescan.

Right-click the canvas to browse loaded functions by category.
Duplicate function names trigger conflict resolution; review the offered
choices before changing the definitions used by an existing pipeline.

## Manage registration

Use **Plugins > Manage Plugins** to inspect registered plugins.
Disabling a plugin is a device preference; it does not delete its files or
remove the pipeline's dependency. Removing a plugin unregisters it from the
project; it does not uninstall a package or delete its source.
**Uninstall** is a separate action that removes the installed distribution
using pip. **Edit** changes local plugin files; **Copy to edit** creates local
source when installed files cannot safely be edited in place.

Pipelines referencing unavailable plugins need those dependencies restored
before their nodes can be used. Moving a local plugin may require selecting its
new configuration path.

!!! warning

    Plugins are executable Python code, not passive data. Loading a path, module,
    or entry point can execute code. Only install and load plugins you trust.

Next: [sharing](sharing.md) to distribute files or export a complete project.
