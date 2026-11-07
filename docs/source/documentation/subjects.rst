FreeSurfer subjects
===================

Select a directory
------------------

By default, mne-nodes looks under ``<BIDS-root>/derivatives/freesurfer``.
If that folder contains a ``subjects`` directory, it uses that directory.

To use another location, choose **BIDS > FreeSurfer subjects directory...**
and select the folder containing subject folders. Changing the directory does
not move files. This choice is remembered per dataset on the current device.

Import reconstructions
----------------------

1. Choose **BIDS > Import FreeSurfer subjects...**, or open the same importer
   from the coregistration dialog.
2. Select one subject folder, or choose a subjects directory and check the
   subjects to import.
3. Click **Import selected subjects**.

The importer copies reconstructions into the selected subjects directory.
It does not create reconstructions or overwrite existing subjects. Allow
sufficient disk space and verify that each MRI belongs to the correct
participant. See :doc:`coregistration` to match recordings to an MRI.
