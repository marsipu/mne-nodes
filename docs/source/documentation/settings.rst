Settings
========
There are two different ways, application settings are stored in MNE-Nodes.
It depends on whether the settings is device-specific or project-specific.
For device-specific settings, such as the number of jobs or whether cuda is enabled, are stored either with *Settings* in a JSON file located in an OS-dependent directory.
The user-specific settings are used to store user preferences, such as the image format or the appearance of the GUI.
These settings are stored in the configuration file used to configure a project.

Dataset and output folders
--------------------------
When switching to another pipeline configuration, MNE-Nodes asks whether to keep
the current BIDS root, even if both configurations use the same dataset name.
Choosing No opens a folder picker for a different BIDS root. Keeping the same
root preserves the loaded configuration's input selections and custom groups,
unless its recorded dataset name differs from the dataset at that root.

Derivative and plot roots are reset whenever the active configuration file
changes. During setup, select one parent folder: MNE-Nodes creates
``<config-name>_derivatives`` and ``<config-name>_plots`` within it. Plots are
saved directly in the config-specific plots folder, without an additional
config-name subfolder. Existing output files are not moved or deleted.
The welcome tour uses its packaged pipeline name, ``Welcome``, so output setup
does not ask for a pipeline name.
Explicitly assigned output roots remain supported; legacy plot roots still use
their config-name subfolder.
