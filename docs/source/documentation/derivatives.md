# Save processing results

Choose **BIDS > Derivative storage...** to use the default
`<BIDS-root>/derivatives/mne-nodes` folder or select a separate writable
folder. Changing this location does not move existing results.

Enable the **Save** checkbox on a function node to save its results when the
plugin provides a writer. Without it, results still pass to downstream nodes
in memory. Not every node has a writer.

To start at a later node, first save the required upstream results and ensure
the plugin provides readers for them. The application reads them from the
currently selected derivative folder.

!!! warning

    Pipelines sharing a derivative folder can target the same output files.
    Check writer overwrite settings and your output location before running.
    With non-FIF recordings, a saved file may retain the input extension even
    if the writer produces FIF content.

Coregistration transformations also use the selected derivative folder.
