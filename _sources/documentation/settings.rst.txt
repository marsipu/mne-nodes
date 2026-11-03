Settings
========
FreeSurfer/WSL setup uses automatic environment discovery without installation-path
settings. **BIDS > FreeSurfer setup...** provides a discovery check and an optional
WSL distribution selector; see :doc:`freesurfer`.

Open **Settings...** in the menu bar to change the application theme, Qt style,
font, font size, startup window size, node pipe style, and console word wrapping.
Settings are grouped into **Appearance**, **Node Editor**, and **Console** tabs.
Descriptions below each setting explain its effect. Changes are saved
immediately; appearance and startup window-size changes require a restart.
Pipe style and console wrapping apply immediately and stay synchronized with
the corresponding **View** menu controls.

Device-specific preferences are stored by ``Settings`` in ``settings.json`` in
the platform's application configuration directory. ``MNENODES_SETTINGS_DIR``
can override this directory (or specify a JSON file directly). Pipeline-specific
parameters remain in the pipeline configuration file.

The packaged ``src/mne_nodes/resources/settings.toml`` defines the settings
dialog's widget types, defaults, labels, descriptions, tabs, restart requirements,
and widget options. Each setting's ``tab`` field assigns its tab; tabs and rows
follow their first appearance in the TOML file.
Font families and Qt styles are discovered on the current
device. Add editable settings there rather than hard-coding dialog rows or
duplicating their defaults in Python. Internal state such as recent paths and
plugin configuration is not exposed in the dialog. User values remain in JSON;
the TOML file describes the available settings and is not modified by the GUI.

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

FreeSurfer subjects default to
``<BIDS-root>/derivatives/freesurfer/subjects`` when that directory exists;
otherwise ``<BIDS-root>/derivatives/freesurfer`` is used directly.
The nested layout takes precedence if both exist; roots are not merged.
This location is independent of the processing derivative root.
Use **BIDS > FreeSurfer subjects directory...** to choose another existing
directory or restore **Dataset default**. The chosen directory is used directly
and remembered separately for each BIDS dataset on this device. Existing files
are not moved; missing chosen directories cause an error rather than a fallback.
MNE-Nodes sets the process-local ``SUBJECTS_DIR`` environment variable without
modifying MNE-Python's saved configuration. The default directory is created when a
FreeSurfer operation needs it (using the direct layout for a new dataset);
existing segmentations and new imports use the same resolved directory.

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
Explicitly assigned output roots remain supported; legacy plot roots still use
their config-name subfolder.

Plot windows
------------
Pipelines run in a separate process. Plot windows opened by a pipeline, such as
the Qt raw browser, Matplotlib figures or PyVista 3D figures, would close as
soon as this process finishes. With **Settings > Keep Plots Open** enabled
(device setting ``keep_plots_open``, enabled by default), the process instead
waits after the pipeline finished until all of its plot windows were closed.
Disable it to let pipeline processes exit right away.
