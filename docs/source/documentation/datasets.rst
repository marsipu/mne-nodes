BIDS dataset requirements
=========================

MNE-Nodes expects an existing BIDS dataset, not a directory of arbitrary raw
recordings. Select the dataset root (the folder containing
``dataset_description.json``) using **Set BIDS Root**. Preparing or validating a
BIDS dataset is a separate step: use MNE-BIDS to convert recordings and a BIDS
validator to check the dataset before processing.

Raw data and metadata
---------------------

* Include ``dataset_description.json`` with the BIDS-required metadata, including
  ``Name`` and ``BIDSVersion``. MNE-Nodes uses ``Name`` to identify the dataset.
* Put recordings in BIDS subject folders, optional session folders, and the
  corresponding ``meg``, ``eeg``, or ``ieeg`` datatype folder. Keep BIDS entity
  labels and filenames consistent. Use a recording format supported by the
  installed MNE-Python and MNE-BIDS versions.
* Keep all required metadata and companion files with the recordings. For example,
  a BrainVision recording needs its header, marker and binary files, not just the
  header. Include the applicable JSON sidecars, channel tables, event tables,
  electrode positions and coordinate-system metadata.
* Select a writable derivative location (see below). The BIDS root itself needs
  to be writable for dataset-local derivatives and FreeSurfer imports.
  The import and coregistration workflows do not modify raw recordings.

The input node exposes ``info`` (measurement metadata), ``event_id`` (the
event-name-to-code mapping from the BIDS recording), and ``trans`` (a saved
head-to-MRI transformation) as connectable outputs.
These are non-selectable data types: they have no separate tabs in the input
widget or independent file selections. Select recordings in the EEG, MEG or
iEEG tabs, or select a recording group, and connect the metadata outputs to
functions that need them. A raw-data connection is not required.

Associated auxiliary data and overview
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Use **BIDS > Set BIDS root...** or **Set BIDS Root** on the input node to select
the dataset. Both entry points use the same folder chooser; canceling leaves
the current dataset unchanged.

Use **BIDS > Data overview...** or **Data overview** on the input node to inspect
the dataset. The read-only, refreshable table has one row per participant
recording, identified by its BIDS filename rather than its full path. Columns
indicate the presence of anatomical candidates, a resolved FreeSurfer subject,
a head-to-MRI transformation, and an associated empty-room recording using check
and cross icons. Warning icons distinguish lookup errors from missing data;
``N/A`` indicates that empty-room data does not apply to non-MEG recordings.
Hover over a cell for details. Columns can be sorted by recording name or
availability. Anatomy is matched by BIDS subject and compatible session, not
asserted to be the correct MRI. Dataset totals include unassociated anatomy,
reconstructions and empty-room recordings, without a separate file-path list.
Discovery runs in a WorkerDialog with a busy indicator during dataset discovery,
then a progress bar and recording name while associations are checked. Empty
datasets finish with zero recordings. Discovery does not load raw signal samples.
The table uses a model-backed view with cached icons rather than allocating an
item per cell,
and does not access the filesystem while painting or sorting.

Empty-room MEG recordings are associated inputs, not independent selections.
They have no selection tab and are excluded from participant recording groups.
The ``raw_er`` output is compatible with ``raw`` inputs: connect it, for example,
to a raw-covariance node to use empty-room data instead of the participant's raw
recording. Association lookup follows MNE-BIDS: use ``AssociatedEmptyRoom`` from
the MEG sidecar, otherwise its measurement-date matching. A missing, broken or
ambiguous association disables ``raw_er`` and is an error during execution.
**Every** selected recording must have an association; mixing EEG recordings
with MEG recordings therefore disables this output. Group execution returns one
empty-room Raw per member, retaining the member order.

The input node shows ``raw_er`` only when MEG empty-room data exists in the
dataset (``sub-emptyroom`` or ``task-noise``), and ``subject`` only when a
FreeSurfer reconstruction exists. Dataset presence alone does not enable these
outputs: they must also be available for every selected recording. Existing
wiring is preserved if auxiliary data disappears; the unavailable port is
hidden and disabled until the data returns.

Running FreeSurfer reconstruction from anatomical data and skipping completed
reconstructions across runs are future features, not part of this association
handling. Existing reconstructions continue to supply the ``subject`` output.

Visible outputs are dimmed and disabled when unavailable for the current selection;
hover over a disabled output for the reason. ``trans`` requires a transformation
for **every** selected recording, using the same recording-specific and
unambiguous session-level lookup as coregistration. ``subject`` requires a
matching FreeSurfer reconstruction for every selected recording. Saved
coregistration subject associations take precedence over ``sub-<label>`` or
``<label>`` name matching. A group must map to one MRI subject when using the
``subject`` output.
FreeSurfer reconstructions have no separate input tab or selection. The
``subject`` output is derived from the selected recordings and their
coregistration associations. Subject-based recording groups remain available
in the Groups tab; they select recordings, not reconstructions.

Within a pipeline run, output-producing non-method nodes whose inputs depend
only on the resolved MRI subject are computed once per node and MRI subject.
This includes chains such as BEM surfaces followed by a BEM solution, or source
space setup. Recordings mapped to the same reconstruction reuse those results.
Nodes using recording-dependent inputs (for example ``info``, ``trans`` or raw
data in a forward solution) still run for each recording. Reused results are
copied so downstream in-place changes do not alter the cached result.
The cache is reset for each run, and distinct nodes retain their own parameters
and results. Existing output-saving behavior is unchanged; this cache does not
introduce loading or invalidation of derivatives between runs.

All recording-type outputs require a selection, even when matching data exists
in the dataset. For example, ``meg`` is disabled until at least one MEG recording
is selected directly or through a group; selecting only EEG recordings does not
enable ``meg``. With nothing selected, all input-node outputs are disabled.
``anat`` likewise requires a selected anatomical file in the anatomy tab;
selecting raw recordings does not automatically select anatomy. Other selectable
file types follow the same rule, and selected files must exist on disk.
With no raw recordings selected, metadata and subject outputs remain disabled
even when anatomical files are selected.
Changing selections, saving transformations, changing the derivative root, or
importing subjects refreshes availability without removing existing connections.
Checkbox changes reuse the input node's known datatypes and empty-room inventory
instead of rescanning all recording files. Association checks still use the
current selection and stop once an output is known to be unavailable. Use the
data overview's **Refresh** or refresh the input node after adding external data
to rescan the inventory.
Unavailable connections are retained when saving and reopening a pipeline, but
cannot be created interactively. Missing or ambiguous transformations and missing
MRI subjects raise an error during execution rather than silently skipping data.

Output colors
-------------

Output ports use an MNE-logo-derived semantic palette on both input and function
nodes:

.. list-table::
   :header-rows: 1

   * - Category
     - HEX
     - Examples
   * - Raw sensor data
     - ``#fce104``
     - Raw, MEG, EEG, iEEG, raw_er, info, events and event_id
   * - Processed sensor-space data
     - ``#e6441a``
     - Epochs, evoked responses, ICA, covariance and time-frequency results
   * - Raw anatomical/source-space data
     - ``#3348cd``
     - Subject, anatomy and MRI
   * - Processed source-space data
     - ``#01feff``
     - Transformations, forward/inverse operators, source spaces and estimates

Input-node outputs follow the category order above: raw sensor data, processed
sensor data, raw anatomy/source data, then processed source data. Types within
each category use the central datatype registry order; unclassified types come
last, alphabetically. Refreshing or reopening a pipeline retains this order
without replacing ports or dropping their connections.

Disabled outputs retain their category color but are dimmed. Connected and
hovered outputs retain the same color; temporary connection-compatibility
highlights still indicate valid and invalid connections. Unclassified outputs
retain the default port styling. For custom output names, accepted datatype
aliases supply a color only when their known types belong to one category.

Input-node datatype tabs reuse this palette as thin, translucent underline
accents, slightly stronger on the selected tab. The content frame also has a thin,
muted border matching the selected datatype. Labels and backgrounds retain the
application theme. The Groups tab and unclassified datatypes remain neutral.

The palette and datatype assignments are managed centrally in
``mne_nodes.gui.colors``. This is the shared starting point for future coloring
of nodes, parameters and other application components; those components are
not recolored by this change.

Example dataset layout
----------------------

An example dataset layout is::

    dataset/
        dataset_description.json
        participants.tsv
        sub-01/
            ses-01/
                meg/
                    sub-01_ses-01_task-rest_run-01_meg.fif
                    sub-01_ses-01_task-rest_run-01_meg.json
                    sub-01_ses-01_task-rest_run-01_channels.tsv
                anat/
                    sub-01_ses-01_T1w.nii.gz
        derivatives/
            freesurfer/
                subjects/
                    sub-01/
                        mri/
                        surf/
                        label/
                        bem/
            mne-nodes/
                sub-01/
                    ses-01/
                        meg/
                            sub-01_ses-01_task-rest_run-01_epo.fif
                            sub-01_ses-01_task-rest_run-01_ave.fif
                            sub-01_ses-01_task-rest_run-01_trans.fif

This is an illustrative layout, not a complete list of BIDS-required files.
An anatomical BIDS image is optional for electrophysiology-only processing.
FreeSurfer reconstructions are also optional unless an operation needs an MRI
subject. A T1-weighted image alone is not a FreeSurfer reconstruction.

Derivative storage
------------------

Open **BIDS > Derivative storage...** to choose between:

* **Inside BIDS dataset** (default): outputs go to
  ``<BIDS-root>/derivatives/mne-nodes``. This folder is created automatically.
* **Separate derivatives root**: select/create a writable output directory,
  for example on another disk. The selected directory is the derivative root
  itself; MNE-Nodes does not append ``derivatives`` or ``mne-nodes`` to it.

The choice is remembered in this device's settings for the active pipeline.
Canceling either dialog keeps the previous location. Changing the location
does not move, copy or delete existing derivatives. Select the old root again
to reuse those files. Existing explicitly configured roots are retained, even
if they use an older folder layout. If an explicit root is missing, output
initialization fails rather than silently saving somewhere else.

Processing results such as epochs and evoked responses are derivative files,
not additions to the raw recording folders. Enable a function node's checkbox
to save outputs for which the plugin provides a write function. Unchecked nodes
still pass their results to connected nodes in memory, but do not save them.
The plugin's output metadata determines the writer and filename suffix;
typical MNE outputs use ``*_epo.fif`` for epochs and ``*_ave.fif`` for evoked
responses. Not every output type has a disk writer.

For recording-level outputs, MNE-Nodes preserves the input BIDS entities
(subject, session, task, run, etc.) and datatype directory, substitutes the
output suffix, and uses the selected derivative root. For example, epochs
from ``sub-01/ses-01/meg/sub-01_ses-01_task-rest_run-01_meg.fif`` go to
``<derivative-root>/sub-01/ses-01/meg/sub-01_ses-01_task-rest_run-01_epo.fif``.
The file format is determined by the writer; these are BIDS-style derivative
paths, not a guarantee that every plugin output meets a BIDS derivative
specification.

Path construction currently retains the input filename extension. For non-FIF
inputs this can leave a nonstandard extension even when the writer stores FIF
content; the FIF filenames above illustrate FIF inputs.

When starting execution at a later node, connected inputs not produced during
that execution are read from the selected derivative root using the plugin's
read function. Save the required upstream outputs first. There is no automatic
fallback search in previous roots. Outputs are not separated by pipeline name:
pipelines using the same root and recording/output suffix can target the same
file. Writer parameters control overwrite behavior.

Coregistration also reads and writes ``*_trans.fif`` files under the selected
derivative root.

FreeSurfer subjects remain dataset-local, even when a separate processing
derivative root is configured. MNE-Nodes uses
``<dataset>/derivatives/freesurfer/subjects`` when that directory exists;
otherwise it uses ``<dataset>/derivatives/freesurfer`` with subject folders
directly inside it. If both layouts exist, the nested ``subjects`` directory
takes precedence; the two roots are not merged. Discovery, imports,
coregistration and pipeline ``subjects_dir`` parameters all use this same root.
No existing files are moved.

FreeSurfer's default ``SUBJECTS_DIR`` is ``$FREESURFER_HOME/subjects``, but it can
be customized (see the `FreeSurfer setup documentation
<https://surfer.nmr.mgh.harvard.edu/fswiki/SetupConfiguration_Linux>`_).
The nested layout is supported, not required by MNE-Nodes.
Global MNE ``SUBJECTS_DIR`` settings and environment variables are not used
to locate dataset subjects. If neither layout exists,
``<dataset>/derivatives/freesurfer`` is created when needed.
Pipeline configuration files can remain
elsewhere. Plot output is optional, may live outside the dataset, and does not
trigger a folder prompt; plot-node-driven prompting is not implemented yet.

Importing existing FreeSurfer subjects
--------------------------------------

Use **BIDS > Import FreeSurfer subjects...**, or **Import FreeSurfer subjects...**
in the coregistration dialog. There are two source-selection options:

* **Choose subject folder...** selects one reconstructed subject, for example
  an existing ``SUBJECTS_DIR/sub-01`` folder.
* **Choose subjects directory...** lists the subject folders directly inside an
  existing FreeSurfer subjects directory. Select the subjects to copy with the
  checkboxes; All and Clear are available.

Click **Import selected subjects** to copy the selected reconstructions into
the dataset's FreeSurfer folder. A candidate must contain ``mri``, ``surf`` and
``label`` directories, matching MNE-Nodes' subject-discovery rules. This structural
check does not certify a complete or successful FreeSurfer reconstruction.
All contents of each selected folder are copied, including additional ``bem``
files if present. The importer does not run FreeSurfer, segment an MRI, generate
missing head surfaces, rename subjects, or establish an anatomical correspondence.

Subject folder names are preserved. Names such as ``sub-01`` or ``01`` can be
matched automatically to BIDS subject ``01`` in coregistration. For other names,
choose the corresponding FreeSurfer subject explicitly. This association is
remembered in the pipeline configuration. Verify that the MRI really belongs
to the participant; a name match is not anatomical validation.

Imports run in a worker progress dialog and can require substantial disk space.
Original folders are not modified. Existing destination subjects and duplicate
names are rejected before copying; there is no merge or overwrite option.
Sources overlapping the destination are rejected. Each subject is copied to a
temporary staging folder and published only after copying finishes. A failed or
canceled subject is cleaned up; already completed subjects remain available.
Cancellation is checked between subjects and after each copy, not during an
individual file copy. Refresh or reopen the importer after resolving a conflict.

Coregistration prerequisites
----------------------------

Head-to-MRI fitting needs usable measurement digitization, including the
appropriate fiducials and head-shape or electrode points. For EEG/iEEG datasets,
preserve electrode and coordinate-system sidecars so MNE-BIDS can reconstruct
the digitization correctly. Recordings without digitization remain visible in
the coregistration manager, but cannot be fitted or grouped as identical.

The selected FreeSurfer subject also needs a head surface readable by MNE
(for example a prepared ``surf/lh.seghead`` or suitable ``bem`` head surface).
The automated fitting recipe estimates MRI fiducials; this also requires the
FreeSurfer MRI information used by MNE to map template fiducials to the subject.
An imported folder that passes structural discovery can still lack these files.
Prepare missing surfaces or MRI metadata with the appropriate MNE/FreeSurfer tools.

Existing transformations are optional. The coregistration manager finds
recording-specific ``*-trans.fif`` derivatives and unambiguous less-specific
session files. New fits are saved as recording-specific derivatives. Recordings
share a digitization group only within the same BIDS subject/session and only
when their digitization matches exactly. Always inspect the resulting alignment.
See :doc:`coregistration` for fitting, saving and reusing transformations.

Changing datasets
-----------------

Switching the BIDS root requires confirmation and clears stale input selections,
including FreeSurfer selections, coregistration subject mappings and custom
groups. The derivative and optional plot settings are reset. Files in the
previous dataset are not moved or deleted. See :doc:`settings` for details.
