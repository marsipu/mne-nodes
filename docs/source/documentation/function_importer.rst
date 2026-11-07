Create a plugin with FunctionImporter
=====================================

The FunctionImporter turns top-level Python functions into node definitions.
It generates configuration, not processing code: you supply the Python function.

Load code
---------

1. Save your functions in a Python file with a valid module name, such as
   ``my_processing.py``. Keep imports and helper code in that file.
2. Open **Plugins > Import Functions...** and click **Load File**.
3. Select a function's editor tab to review its configuration.

This minimal example receives a Raw object and exposes two parameters:

.. code-block:: python

   def example_filter(raw, highpass=1, lowpass=30):
       """Filter a recording."""
       raw = raw.filter(highpass, lowpass)
       return raw

.. figure:: /_static/screenshots/linux/function-importer.png
   :alt: FunctionImporter showing example_filter, its raw input and output, and filter parameters.

   Required arguments become inputs; arguments with defaults become parameters.

Review the definition
---------------------

* **Inputs / Parameters:** use the exchange button to move an argument between
  the two roles. Use the gear button to configure it.
* **Inputs / Outputs:** check accepted connections and whether inputs are
  optional. Readers, writers, and BIDS suffixes are needed for derivative I/O,
  but not for simply passing an object between nodes.
* **Parameters:** choose the widget, default value, and allowed options.
  Literal defaults and docstrings help infer widgets; review unresolved values.
* **target:** ``file`` executes for individual selected files; ``group`` executes
  for selected groups, with grouped recording inputs.
* **Change Function Description:** edit the text presented to users.
* **Run in FreeSurfer environment:** leave disabled for normal Python functions;
  see :doc:`freesurfer` for the separate execution environment.

Prefer explicit return variables, such as ``return raw`` or
``return epochs, evoked``. Return expressions and multiple return branches
cannot be assumed to produce the intended port definitions. Review the outputs
and warnings rather than treating analysis as validation.

Save and use
------------

Click **Save** and complete **Plugin Package Metadata**: distribution name,
version, description, author, license, and additional Python dependencies.
Choose a project-root folder for the new package. Save creates an installable
project, including source, configuration, package metadata, README, and license,
then loads the plugin. It refuses to overwrite existing package files.
Open **View > Node Picker** to add the new nodes.

Git initialization is optional and creates no commits, remotes, or uploads.
**Install package after saving** is also optional; editable installation links
the environment to your source. Loading from a path does not require installation.

The original file loaded for import is not overwritten: its edited function
code is saved into the new package. **Re-analyze Code** updates definitions after
editor changes; recheck custom widget configuration.
For an existing local plugin, **Manage Plugins > Edit** opens source,
configuration, and available package files. Saving there overwrites those local
files and reloads enabled plugins. Installed non-editable files offer
**Copy to edit** instead. External changes are checked before overwriting.

Loading a file normally analyzes its syntax without executing it. Loading the
saved plugin imports Python code and can execute top-level statements.
Use only code you trust. See :doc:`plugins` and :doc:`sharing` for distribution.
