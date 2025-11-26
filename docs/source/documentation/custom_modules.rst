Custom Modules/Functions
========================
To extend the functionality of **mne-nodes**, you can add custom modules.
.. ToDo: From the gui, you can add custom modules by

The configuration file (JSON) is expected to be in the same directory as the module.

Best Practices
--------------
- If you use the same parameter name in multiple functions, the same parameter configuration will be used. If you want different configurations, use different parameter names.

Plot Functions
--------------
There are mutliple possibilities to use plots in a custom function. For example you could plot a matplotlib plot interactively with the PyQt backend. Or you could decide to not show the plot and just save it to a file to use later. To make the plot interactively, make sure to set ``block=True`` for example in ``raw.plot(block=True)`` or with ``plt.show(block=True)``.
