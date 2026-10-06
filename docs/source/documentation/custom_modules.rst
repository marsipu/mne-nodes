Custom Modules/Functions
========================
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
after editing a function. Code text requires a plugin name; when saving, choose
the directory for the new Python module and its configuration. Module imports,
decorators and other supporting code are preserved when saving a plugin from
text. For an existing Python file, **Save** writes the configuration alongside
the original file; it does not overwrite the original Python source.

Saving from the application automatically loads the generated plugin and
refreshes the node picker, making its functions available immediately.
Saving therefore imports the Python module and executes its module-level code;
only save code you trust. If loading fails, an error is displayed and the saved
files remain available for correction and retry.

The configuration file (JSON) is expected to be in the same directory as the module.

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
