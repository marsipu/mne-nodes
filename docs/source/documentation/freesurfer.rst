Use FreeSurfer
==============

Install FreeSurfer and the separate ``mne-nodes_freesurfer`` plugin to use
FreeSurfer nodes. Open **BIDS > FreeSurfer setup...** to check your setup and
see installation guidance. See :doc:`plugins` for loading plugins.

On Windows, install FreeSurfer in WSL using the
`WSL <https://learn.microsoft.com/windows/wsl/install>`_ and
`FreeSurfer <https://surfer.nmr.mgh.harvard.edu/fswiki/DownloadAndInstall>`_
instructions. Configure your FreeSurfer license and shell environment. Python
operations also need MNE installed inside WSL. The setup dialog lets you choose
a WSL distribution if needed.

Use nodes
---------

Select a recording and connect the input node's ``subject`` output to operate
on its matching reconstruction. For a new reconstruction, connect ``anat`` to
``recon-all``; its ``subject`` output can feed subsequent nodes such as
``make_watershed_bem``.

``recon-all`` can take hours and modifies its subject directory. Ensure you have
sufficient disk space and review the inputs before starting.

When importing your own function that needs FreeSurfer, enable
**Run in FreeSurfer environment** in :doc:`function_importer`. Graphical
viewers opened there need a working display in that environment.
