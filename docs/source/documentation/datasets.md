# BIDS dataset requirements

MNE-Nodes expects an existing BIDS dataset, not a directory of arbitrary raw
recordings. Select the dataset root (the folder containing
`dataset_description.json`) using **Set BIDS Root**. Preparing or validating a
BIDS dataset is a separate step: use MNE-BIDS to convert recordings and a BIDS
validator to check the dataset before processing.

## Raw data and metadata

* Include `dataset_description.json` with the BIDS-required metadata, including
  `Name` and `BIDSVersion`. MNE-Nodes uses `Name` to identify the dataset.
* Put recordings in BIDS subject folders, optional session folders, and the
  corresponding `meg`, `eeg`, or `ieeg` datatype folder. Keep BIDS entity
  labels and filenames consistent. Use a recording format supported by the
  installed MNE-Python and MNE-BIDS versions.
* Keep all required metadata and companion files with the recordings. For example,
  a BrainVision recording needs its header, marker and binary files, not just the
  `.vhdr` header selected in mne-nodes. Keep the `.vmrk` and `.eeg` files
  beside it. Include the applicable JSON sidecars, channel tables, event tables,
  electrode positions and coordinate-system metadata.
* Select a writable [derivative location](derivatives.md). The BIDS root needs
  to be writable for dataset-local derivatives and FreeSurfer imports.
  The import and coregistration workflows do not modify raw recordings.

## Example dataset layout

An example dataset layout is:

```text
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
```

This is an illustrative layout, not a complete list of BIDS-required files.
An anatomical BIDS image is optional for electrophysiology-only processing.
FreeSurfer reconstructions are also optional unless an operation needs an MRI
subject. A T1-weighted image alone is not a FreeSurfer reconstruction.

## Changing datasets

Switching the BIDS root requires confirmation and clears stale input selections,
including FreeSurfer selections, coregistration subject mappings and custom
groups. The derivative and optional plot settings are reset. Files in the
previous dataset are not moved or deleted. See [settings](settings.md) for details.

- [Try the sample dataset](sample_data.md)
- [Select recordings and associated data](data_selection.md)
- [Save processing results](derivatives.md)
- [FreeSurfer subjects](subjects.md)
