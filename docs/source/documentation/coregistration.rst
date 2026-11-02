Head-to-MRI coregistration
========================================

Open **BIDS > Coregistration...** to manage head-to-MRI transformations for raw
MEG, EEG and intracranial EEG recordings in the configured BIDS dataset.
Derivatives default to ``<BIDS-root>/derivatives/mne-nodes`` (or a separate root
selected with **BIDS > Derivative storage...**) and FreeSurfer segmentations
are discovered in ``<BIDS-root>/derivatives/freesurfer/subjects`` when present,
otherwise directly in ``<BIDS-root>/derivatives/freesurfer``. Neither default
location requires a folder picker, and a plot folder is not needed.
Use **Import FreeSurfer subjects...** to copy a single existing reconstruction
or selected subjects from an external subjects directory into the dataset.
See :doc:`datasets` for the expected layout, import behavior and prerequisites.

The dialog reads recording headers, including BIDS electrode sidecars, without
preloading signal samples. Recordings are grouped within a BIDS subject and
session only when all digitization points, identifiers and coordinate frames
match exactly. Missing digitization and header-reading errors are shown rather
than treated as matching recordings. Select a group to see every member in the
recording list beside the digitization groups. Check marks indicate transformation
availability, not alignment
quality.

Choose the corresponding **FreeSurfer subject**. Matching ``sub-<label>`` or
``<label>`` names are selected automatically; other segmentation names can be
selected explicitly. The selection is remembered in the pipeline configuration.

* **Automatic coregistration** runs in a progress dialog. It estimates MRI
  fiducials, fits the measured fiducials, performs six ICP iterations with a
  reduced nasion weight, excludes head-shape points at least 5 mm from the
  surface, and performs twenty final ICP iterations. The mean, minimum and
  maximum digitization-to-MRI distances are reported in millimetres. Cancellation
  is checked between stages and before saving.
* **Manual coregistration / inspect** opens MNE-Python's Qt coregistration GUI,
  loading the selected recording's existing transformation when available.
  **Save to derivatives**, including Save when closing the MNE window, writes
  directly to the dataset's configured derivatives root without a filename
  picker. Subject, input recording and MRI scaling controls are locked so that
  the transformation remains associated with the selected unscaled MRI and
  digitization group.
* **Reuse selected transformation for group** copies the selected recording's
  transformation to all members of its verified digitization group.

Both fitting methods save a separate file for each recording, preserving its
BIDS entities and datatype directory, for example::

    <derivatives-root>/sub-01/ses-01/meg/sub-01_ses-01_task-rest_run-01_trans.fif

Split-file entities are removed because the transformation belongs to the whole
recording. Existing recording-specific files take precedence. An unambiguous,
less-specific transformation (for example a session-wide file) is also recognized;
ambiguous alternatives are reported as errors. Existing recording-specific
outputs require confirmation before replacement. Session-wide source files are
not overwritten.

If the configured derivatives root has no matching transformation, every other
pipeline folder in ``<BIDS-root>/derivatives`` (except FreeSurfer) is searched,
so transformations created by preceding software are reused. Files may be
stored directly in the subject or session folder or in a datatype folder, and
the legacy ``-trans.fif`` naming (for example
``sub-01_ses-01_task-rest_run-1-trans.fif``) is recognized. Matches in more than
one folder are reported as ambiguous; saving a transformation in the configured
derivatives root resolves this, because that root takes priority.

Automatic fitting requires usable measured fiducials and a FreeSurfer head
surface. Its quality depends on the MRI and digitization; always inspect the
alignment in the manual GUI, even when the reported distances are small.
The filename-picker integration uses MNE's private Qt widget API and reports an
error if the installed MNE version is incompatible.
