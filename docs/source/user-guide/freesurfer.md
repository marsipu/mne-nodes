# FreeSurfer

MRI-based steps such as BEM models and
[coregistration](coregistration.md) need a FreeSurfer reconstruction of the
participant, called a subject.

## Use existing reconstructions

mne-nodes looks for subjects in `<BIDS-root>/derivatives/freesurfer`, or in
its `subjects` folder if there is one.

| Your reconstructions are | Do this |
| --- | --- |
| In another folder you want to keep using | **BIDS > FreeSurfer subjects directory...** |
| To be copied into the dataset | **BIDS > Import FreeSurfer subjects...** |

The import copies the checked subjects. It never overwrites existing subjects
and never changes the originals.

![The import dialog with two checked subjects](../_static/screenshots/linux/freesurfer-import.png)

## Run FreeSurfer from mne-nodes

You need:

* FreeSurfer with a license. On Windows, install it inside
  [WSL](https://learn.microsoft.com/windows/wsl/install), together with MNE.
* The `mne-nodes_freesurfer` [plugin](plugins.md).

**BIDS > FreeSurfer setup...** explains the installation, and **Discover**
checks whether everything is found.

![The FreeSurfer setup dialog](../_static/screenshots/linux/freesurfer-setup.png)

Then connect the input node to the FreeSurfer nodes:

| To | Connect |
| --- | --- |
| Use an existing reconstruction | The `subject` output to the node |
| Create a reconstruction | The `anat` output to `recon-all`, whose `subject` output feeds nodes such as `make_watershed_bem` |

!!! warning
    `recon-all` can take hours and needs a lot of disk space. Check the inputs
    before you start it.

For your own functions that need FreeSurfer, enable **Run in FreeSurfer
environment** in the [function importer](function_importer.md).
