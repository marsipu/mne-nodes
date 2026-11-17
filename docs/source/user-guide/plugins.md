# Plugins

Plugins provide the functions you add as nodes. mne-nodes itself contains no
analysis functions.

!!! warning
    A plugin is Python code that runs on your computer. Only load plugins you
    trust.

## Load a plugin

Open the **Plugins** menu and choose where the plugin comes from.

![The Plugins menu](../_static/screenshots/linux/plugins-menu.png)

| Menu entry | Use it for | You provide |
| --- | --- | --- |
| **Load Plugin from Path** | A plugin folder on your disk | Its `<name>_config.json`, next to `<name>.py` |
| **Load Plugin from Module** | An installed Python package | The importable module name |
| **Load Plugin from GitHub** | A plugin repository | The repository URL |

Installed plugin packages are also found automatically when the application
starts. When a path plugin is part of a package project, you can install it
while loading; leave the box unchecked to load it directly from its folder.

The functions of a loaded plugin appear in the menu that opens with a
right-click on the canvas. If two plugins define a function with the same name,
a dialog asks which one to use.

## Manage plugins

**Plugins > Manage Plugins** lists all plugins of the pipeline.

![The plugin manager with two enabled plugins](../_static/screenshots/linux/plugin-manager.png)

| Button | Effect |
| --- | --- |
| **Disable** / **Enable** | Switches the plugin off or on for this device. Nothing is deleted. |
| **Remove** | Removes the plugin from the pipeline. Its files and package stay. |
| **Edit...** | Opens the source and node definitions of a local plugin. |
| **Copy to edit...** | Creates an editable local copy of an installed plugin. |
| **Uninstall...** | Uninstalls the plugin package with pip. |
| **Refresh** | Searches the Python environment for newly installed plugins. |

A pipeline whose plugin is missing cannot use those nodes until the plugin is
loaded again. After moving a local plugin, load it from its new path.

Next: [create your own nodes](function_importer.md) or
[share a plugin](sharing.md).
