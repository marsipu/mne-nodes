Custom Modules/Functions
========================
For executable command nodes and FreeSurfer-dependent functions, see
:doc:`freesurfer`.

To extend the functionality of **mne-nodes**, you can add custom modules.
The welcome tour (also available under **Help > Restart Welcome Tour**) explains
the import and plugin-loading options and guides you through importing a
``raw.crop()`` example, reviewing it, saving/loading the plugin, and adding and
connecting its node. The tour uses a temporary plugin destination and removes
the demo plugin and files on completion or cancellation.

Importing functions from the application
----------------------------------------
Choose **Plugins > Import Functions...** and use **Load File** to open a Python
file in the function importer. You can also drop one or more local ``.py`` files
or selected Python code text onto the main window or node canvas.
The standard paste shortcut (``Ctrl+V`` on Windows/Linux) imports clipboard
text when the canvas or main window has focus. Paste inside an editor or
parameter field continues to edit that field normally.

The importer analyzes top-level functions without executing the supplied code.
Review the detected inputs, outputs and parameters, and use **Re-analyze Code**
after editing a function. Code text requires a plugin name. Plugin names must
be ASCII Python module names (identifiers, not keywords). Module imports,
decorators and other supporting code are preserved.

On the first **Save**, complete the package metadata dialog and choose the
project root directory. Supply a distribution name, version (initially
``0.1.0``), description, author/copyright holder and an explicit license choice.
BSD-3-Clause and MIT license texts are provided; other SPDX license expressions
require the complete license text. Author email and repository URL are optional.
List additional Python requirements one per line; ``mne-nodes`` is included
automatically. Dependencies are not guessed from imports. PyPI requirements
must use published names rather than direct URLs. Document separately installed
system tools such as FreeSurfer in the generated README.

The same dialog exposes setup options before any files are written:

* **Initialize a Git repository** is checked when Git is available, with
  ``main`` as the initial branch. Uncheck it to save without Git. Existing
  repositories are left unchanged; no commits, remotes or uploads are created.
* **Install package after saving** is optional and unchecked initially.
  **Editable installation** is selected by default: pip links the installation
  to the local source instead of copying it into the environment. Uncheck
  editable installation for a normal install.

Git or installation failures are reported explicitly. Saved files remain
available, and retrying Save retries the failed setup step without recreating
the project or overwriting its metadata.

Saving creates a complete project, using the same structure as the
``mne-functions``, ``simple-functions`` and ``mne-io-functions`` packages::

    pyproject.toml
    README.md
    LICENSE
    .gitignore
    src/
        mne_nodes_<plugin_name>/
            __init__.py
            <plugin_name>.py
            <plugin_name>_config.json

The generated project uses Hatchling, includes its JSON resources in wheels
and source distributions, and registers an ``mne_nodes.plugins`` entry point.
It uses a static version and can build without Git. Existing role-model
packages retain their Git-based versioning with an archive fallback.
Existing destination files are never overwritten on initial creation.
Imported source files are left untouched; editor changes are written to the
new package. Subsequent saves in the same importer update only its generated
source and configuration, preserving manually edited project metadata.
Local helper modules, relative-import dependencies and extra data files are
not copied automatically: add them to the import package before loading or
publishing it.

Saving from the application automatically loads the generated plugin and
refreshes the node picker, making its functions available immediately.
Saving therefore imports the Python module and executes its module-level code;
only save code you trust. If loading fails, an error is displayed and the saved
files remain available for correction and retry.

For local loading, select the JSON under ``src/mne_nodes_<plugin_name>`` using
**Plugins > Load Plugin from Path**. Legacy standalone script/JSON pairs are
still supported. The configuration and implementation script must be siblings;
package plugins also have an ``__init__.py`` declaring ``PLUGIN_NAME``,
``CONFIG_PATH`` and ``SCRIPT_PATH``. Local package loading supports relative
imports.

When loading a configuration path belonging to a package, a dialog offers the
same optional installation and editable-install choice before loading.
Installation is not required for path-based activation. Ordinary packages
installed from a package index are not made editable retroactively; use a local
source project for editable development.

Building, installing and publishing
----------------------------------------
Review the generated metadata, dependencies, README and licensing before release.
The distribution name must be available on the target package index and its
version must increase for each release. In the generated project root::

    python -m pip install build twine
    python -m build
    python -m twine check dist/*
    python -m twine upload dist/*

For local development use ``python -m pip install -e .``; for ordinary
installation use ``python -m pip install .`` or install the built wheel.
Restart any running application after changing an editable installation's
package layout.

Installed plugin discovery
--------------------------
**Plugins > Manage Plugins** lists registered plugins and installed registrations
from ``importlib.metadata.entry_points(group="mne_nodes.plugins")``.
Newly discovered installed plugins are imported and enabled automatically at
startup and when opening the manager. Only install plugin code you trust.
Use **Refresh installed plugins** to detect packages installed externally while
MNE-Nodes is running. Enabled/disabled status is color-coded and each plugin
shows its number of available node definitions, including while disabled.
Failed plugins remain visible with an error instead of appearing enabled.
The project stores both the distribution name and the entry-point name, so
plugin display names need not match Python import names and identically named
registrations from different distributions remain distinguishable.

Explicitly disabled plugins stay disabled across discovery, restarts and
project changes on this device. Existing path-based registrations are preserved
instead of being replaced by installed versions. **Manage Plugins** can disable
plugins without uninstalling packages or deleting files. Installed plugins remain
discoverable, so use Disable rather than Remove; Remove is available for other
registrations. A missing or broken selected entry
point is reported, not silently skipped. A repository URL in package metadata
does not cause an installed plugin to be reloaded from GitHub.

Editing existing plugins
-------------------------
Choose **Plugins > Manage Plugins > Edit...** on the plugin's row.
This opens the function importer, not a separate plugin editor. Its source tab
edits the complete implementation module; select a function on the right to
configure its inputs, outputs, parameters and target. Existing configurations
are preserved until explicitly edited or re-analyzed. Imported functions and
configured class methods are available even if the script has no function
definitions. Additional tabs expose existing package configuration and metadata
(``pyproject.toml``, ``README.md`` and ``LICENSE``), without recreating the package.

Local projects and editable-install source trees are edited in place.
Ordinary installed package files are never edited in the Python environment.
For these packages, **Edit...** offers to copy the plugin into a new local
project first. The copy includes sibling helper modules and resources.
Choose appropriate metadata, preserving the original licensing and attribution.
Saving the copy switches this project's registration to the local copy, while
leaving the original installation unchanged.

Python and TOML syntax and node-configuration structure are validated before
changed files are written.
Files changed externally while the editor is open are not overwritten.
Saving reloads an enabled plugin without changing its activation source;
disabled plugins remain disabled. Reload failures are reported separately
from save failures, and can be retried. Closing with unsaved edits offers
Save, Discard or Cancel.

If a local plugin moves, select its configuration file once when prompted.
The new location is retained for this device. Legacy filename-based
registrations are merged into the plugin's declared name, so relocation does
not add a duplicate registration or prompt again on the next start.

Metadata changes affecting dependencies, entry points or package versions
require reinstalling the package to update its installed distribution metadata.
The editor does not automatically install dependencies, commit files or upload
anything.

Functions provided by a plugin or its implementation script take precedence.
For configured functions that are not exposed there, the loader uses the
``module_name`` metadata to import them from their declared module. For example,
``make_watershed_bem`` is resolved from ``mne.bem``, not the top-level ``mne``
namespace. Class methods continue to be called on their instances.

Inputs
------
The inputs are expected to be all arguments from the function without a default value (args).
Their name needs to be identical to the names of return statements from other functions.

Outputs
-------
Outputs need to be a name variable that is returned from the function. If you want to return static values, just define any variable so they can appear as outputs in the nodes.

Parameters
----------


Plot Functions
--------------
There are mutliple possibilities to use plots in a custom function. For example you could plot a matplotlib plot interactively with the PyQt backend. Or you could decide to not show the plot and just save it to a file to use later. To make the plot interactively, make sure to set ``block=True`` for example in ``raw.plot(block=True)`` or with ``plt.show(block=True)``.
