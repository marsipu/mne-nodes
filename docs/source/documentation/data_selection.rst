Select recordings and associated data
=====================================

Choose a dataset with **BIDS > Set BIDS root...** or **Set BIDS Root** on the
input node. Select recordings in the EEG, MEG, or iEEG tab, or select groups
in **Groups**. See :doc:`datasets` for the expected dataset layout.

Use **BIDS > Data overview...** to check which recordings have matching
anatomy, FreeSurfer subjects, transformations, and empty-room recordings.
Hover over a table cell for details. Matching filenames do not guarantee that
the MRI or transformation is correct.

Connect associated data
-----------------------

The input node offers associated ``info``, ``event_id``, ``anat``, ``subject``,
``trans``, and ``raw_er`` outputs when available. They correspond to the
selected recordings; you do not select them separately.

Ports are disabled if required data is missing or ambiguous for any selected
recording. Hover over the port for the reason. In particular:

* ``anat`` needs a matching T1w image; ``subject`` needs a FreeSurfer
  reconstruction. See :doc:`subjects`.
* ``trans`` needs a head-to-MRI transformation. See :doc:`coregistration`.
* ``raw_er`` needs an associated MEG empty-room recording for each selection.

After adding data outside the application, refresh the data overview or the
input node. Existing connections are retained when associated data becomes
unavailable, but cannot be used until it is available again.
