# Datasets and recordings

mne-nodes reads recordings from a [BIDS](https://bids.neuroimaging.io/) dataset.
It does not convert raw files: create the dataset with
[MNE-BIDS](https://mne.tools/mne-bids/) and check it with a BIDS validator first.

## Try the sample dataset

**BIDS > Add Sample BIDS Data** downloads the MNE sample data (large) into a
folder you choose and selects it. It contains a MEG recording, an MRI, a
FreeSurfer reconstruction, and a head-to-MRI transformation.

![The BIDS menu with Add Sample BIDS Data](../_static/screenshots/linux/bids-menu.png)

## Use your own dataset

Click **Set BIDS Root** on the input node and select the folder that contains
`dataset_description.json`.

```text
dataset/
    dataset_description.json        <- needs Name and BIDSVersion
    sub-01/
        ses-01/
            meg/                    <- or eeg/, ieeg/
                sub-01_ses-01_task-rest_meg.fif
                sub-01_ses-01_task-rest_meg.json
                sub-01_ses-01_task-rest_channels.tsv
            anat/                   <- optional
                sub-01_ses-01_T1w.nii.gz
    derivatives/
        freesurfer/                 <- optional reconstructions
        mne-nodes/                  <- results are saved here
```

* Keep all companion files with a recording, for example the `.vmrk` and `.eeg`
  files of a BrainVision `.vhdr` header.
* The dataset folder must be writable, unless you store
  [results](derivatives.md) and FreeSurfer subjects elsewhere. Raw recordings
  are never modified.
* Switching to another dataset clears selections, groups, and folder settings
  after a confirmation. No files are moved or deleted.

## Select recordings

Check the recordings to process in the tab of their datatype.

![The input node with a checked recording](../_static/screenshots/linux/select-recordings.png)

To process recordings together, switch to **Groups** and group them by subject,
session, run, task, or your own custom groups.

![The Groups tab of the input node](../_static/screenshots/linux/groups.png)

## Associated data

Besides the recordings, the input node offers data that belongs to them. You
do not select it separately.

| Port | Provides | Needs |
| --- | --- | --- |
| `info`, `event_id` | Measurement info and events | The recording |
| `anat` | Anatomical image | A matching T1w image |
| `subject` | FreeSurfer subject | A [reconstruction](freesurfer.md) |
| `trans` | Head-to-MRI transformation | A [coregistration](coregistration.md) |
| `raw_er` | Empty-room recording | An associated MEG empty-room recording |

A dimmed port is missing or ambiguous for at least one selected recording.
Hover over it for the reason.

## Check what is available

**Data overview** on the input node lists what was found for every recording.
Hover over a cell for details, and click **Refresh** after adding files outside
the application.

![The data overview table](../_static/screenshots/linux/data-overview.png)

!!! warning
    A match by file name does not prove that an MRI or a transformation belongs
    to the participant or is correct.
