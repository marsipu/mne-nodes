Custom Modules/Functions
========================
To extend the functionality of **mne-nodes**, you can add custom modules.
.. ToDo: From the gui, you can add custom modules by

The configuration file (JSON) is expected to be in the same directory as the module.

Inputs
------
The inputs are expected to be all arguments from the function without a default value (args).
Their name needs to be identical to the names of return statements from other functions.

Outputs
-------

Parameters
----------


Plot Functions
--------------
There are mutliple possibilities to use plots in a custom function. For example you could plot a matplotlib plot interactively with the PyQt backend. Or you could decide to not show the plot and just save it to a file to use later. To make the plot interactively, make sure to set ``block=True`` for example in ``raw.plot(block=True)`` or with ``plt.show(block=True)``.
