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

Changing the BIDS root or FreeSurfer ``subjects_dir`` asks for confirmation.
Either change resets custom groups, derivative roots, and plot roots, but keeps
the other input directory unchanged. A BIDS-root change clears all input
selections except for data-type ``subject``; a ``subjects_dir`` change clears
only data-type ``subject`` selections. A dataset-name mismatch likewise
preserves these FreeSurfer selections. Declining the confirmation or selecting
the same directory leaves selections, groups, and output roots unchanged.

Derivative and plot roots are reset whenever the active configuration file
changes. During setup, select one parent folder: MNE-Nodes creates
``<config-name>_derivatives`` and ``<config-name>_plots`` within it. Plots are
saved directly in the config-specific plots folder, without an additional
config-name subfolder. Existing output files are not moved or deleted.
The welcome tour uses its packaged pipeline name, ``Welcome``, so output setup
does not ask for a pipeline name.
If a different BIDS root is selected when starting the tour, the sample BIDS
dataset is prepared in that destination before the tour's input node is loaded.
Explicitly assigned output roots remain supported; legacy plot roots still use
their config-name subfolder.
