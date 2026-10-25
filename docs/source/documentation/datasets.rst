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

FreeSurfer subjects always live in ``<dataset>/derivatives/freesurfer``, even when
a separate derivative root is configured. Global MNE ``SUBJECTS_DIR``
settings and environment variables are not used to locate dataset subjects.
The folder is created when needed. Pipeline configuration files can remain
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
