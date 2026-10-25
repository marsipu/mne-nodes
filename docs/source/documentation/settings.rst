Settings
========
There are two different ways, application settings are stored in MNE-Nodes.
It depends on whether the settings is device-specific or project-specific.
For device-specific settings, such as the number of jobs or whether cuda is enabled, are stored either with *Settings* in a JSON file located in an OS-dependent directory.
The user-specific settings are used to store user preferences, such as the image format or the appearance of the GUI.
These settings are stored in the configuration file used to configure a project.

Dataset and output folders
--------------------------
See :doc:`datasets` for the dataset layout and FreeSurfer import options.

When switching to another pipeline configuration, MNE-Nodes asks whether to keep
the current BIDS root, even if both configurations use the same dataset name.
Choosing No opens a folder picker for a different BIDS root. Keeping the same
root preserves the loaded configuration's input selections and custom groups,
unless its recorded dataset name differs from the dataset at that root.

Derivatives default to ``<BIDS-root>/derivatives/mne-nodes``, created automatically
without a folder picker. Use **BIDS > Derivative storage...** to choose this
dataset-local location or select a separate derivatives root, including outside
the dataset. The chosen directory is used directly, without a pipeline-name
subfolder. Existing files are not moved or deleted when changing roots.
Explicit roots from older settings are retained. A missing explicit root causes
an error rather than silently redirecting outputs.

FreeSurfer subjects are stored in ``<BIDS-root>/derivatives/freesurfer``.
This location is independent of the processing derivative root and cannot be
selected separately. MNE-Nodes neither reads nor modifies the global MNE
``SUBJECTS_DIR`` setting for this purpose. The directory is created when a
FreeSurfer operation needs it; existing segmentations are discovered there.

Changing the BIDS root asks for confirmation and resets all input selections,
including FreeSurfer subjects, coregistration subject mappings, custom groups,
and output-folder settings. A dataset-name mismatch likewise clears all input
selections and mappings. Declining the confirmation or selecting the same
directory leaves this state unchanged.

Output-folder settings are reset whenever the active configuration file
changes. Derivatives then default to the active dataset's
``derivatives/mne-nodes`` folder; select a separate root again if needed.
Plots are optional: startup, configuration switches, and coregistration do not
create a plot directory or ask for one. Plot-node-driven prompting is reserved
for a future feature. A plot root may be assigned explicitly outside the dataset;
such roots retain the pipeline-name subfolder layout for exports. Setting
``plot_root`` to ``None`` disables that optional location.

The welcome tour uses its packaged pipeline name, ``Welcome``.
If a different BIDS root is selected when starting the tour, the sample BIDS
dataset is prepared in that destination before the tour's input node is loaded.
