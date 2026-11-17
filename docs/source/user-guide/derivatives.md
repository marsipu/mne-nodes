# Save results

By default, results are only passed from node to node in memory. Check **Save**
on a node to also write its results to disk.

![A node with the Save checkbox checked](../_static/screenshots/linux/save-results.png)

The checkbox appears only if the plugin defines a writer for the node's output.

## Where results go

Results are stored in `<BIDS-root>/derivatives/mne-nodes`. To use another
folder, choose **BIDS > Derivative storage...**. Existing results are not
moved. Coregistration transformations are stored in the same folder.

## Start from saved results

When you run only part of a pipeline with **Start selected nodes**, the results
of the skipped nodes are read from this folder. That requires that they were
saved before and that the plugin defines a reader for them.

!!! warning
    Pipelines that share a results folder can overwrite each other's files.
    Check the folder before you run. For recordings that are not FIF, a saved
    file can keep the original extension although its content is FIF.
