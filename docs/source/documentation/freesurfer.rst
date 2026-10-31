FreeSurfer commands and Python functions
========================================

Open **BIDS > FreeSurfer setup...** to discover installations and view
installation instructions. This does not install software or start processing.
The ``recon-all`` and ``make_watershed_bem`` nodes belong to the separate
``mne-nodes_freesurfer`` plugin, not the core application. Install that package
and it is automatically enabled at startup. Use **Plugins > Manage Plugins**
to refresh discovery or toggle it, or load
its ``src/mne_nodes_freesurfer/freesurfer_config.json`` through
**Plugins > Load Plugin from Path** without installing it.
Connect the input node's
``subject`` port to operate on the MRI subject assigned to each recording.
Subject-only commands run once per MRI subject per node in a pipeline run.
``recon-all`` can take hours and modifies its subject; it is never run by tests.
For a new subject, select a T1 image in the input widget's ``anat`` tab and
connect the input node's ``anat`` port to ``recon-all``. Code generation passes
the image path, not loaded image data. The command derives ``sub-<label>`` from
the BIDS image, and outputs that subject
after successful reconstruction for downstream nodes such as ``make_watershed_bem``.

Automatic environment discovery
-------------------------------
No executable paths need to be configured for a normal installation:

* On Windows, commands run in the default WSL distribution. An interactive
  login Bash shell loads terminal initialization (including ``.bashrc``), so
  ``FREESURFER_HOME``, ``PATH`` and ``FS_LICENSE`` set there are available.
* FreeSurfer is resolved from that environment, ``recon-all`` on PATH, or
  standard installation directories under ``/usr/local/freesurfer``,
  ``/opt/freesurfer`` and ``/Applications/freesurfer``.
* Python calls on WSL use the first Python that can import MNE: shell PATH
  first, then Conda's environment registry and standard Miniconda, Miniforge
  and Anaconda directories. Activating the desired environment in shell startup
  gives it precedence.
* On Linux/macOS, commands run natively and Python calls use MNE-Nodes' current
  Python interpreter.

There are no FreeSurfer or Python installation-path settings. To prioritize an
installation, configure ``FREESURFER_HOME`` and activate the desired Python
environment in your shell startup. The setup dialog offers only an optional
``wsl_distribution`` selector; leaving it empty uses the default distribution.
Discovery is read-only and does not save discovered paths.

FreeSurfer setup is sourced in the child process, never in the application's
environment. ``SUBJECTS_DIR`` is then set to this dataset's subjects directory
(see :doc:`settings`). Windows absolute file paths, including UNC paths, are
translated with WSL's ``wslpath``. Arguments remain separate argv tokens;
shell substitutions, pipelines and redirections are not evaluated.
Output is streamed to the pipeline console, including the final output lines;
nonzero exit codes fail the pipeline rather than appearing successful.

Installation
------------
On Windows, install WSL and a Linux distribution using Microsoft's
`WSL instructions <https://learn.microsoft.com/windows/wsl/install>`_.
Inside that distribution, follow the
`FreeSurfer installation instructions
<https://surfer.nmr.mgh.harvard.edu/fswiki/DownloadAndInstall>`_
and register a license. Configure FreeSurfer and ``FS_LICENSE`` in your Linux
shell startup as described by FreeSurfer.

For Python calls, install Miniforge/Miniconda inside WSL, then create a dedicated
environment (a graphical MNE installation is unnecessary for watershed)::

    conda create -n mne --override-channels -c conda-forge mne-base nibabel
    conda run -n mne python -c "import mne; print(mne.__version__)"

MNE must be installed inside WSL even when already installed on Windows.
Custom Python functions also need their importable package/dependencies installed
in the Linux environment. MNE-Nodes itself need not be installed in WSL.
Compatible MNE/numpy versions on both sides are recommended when returning
Python objects.

Plugin configuration
--------------------
Set ``"uses_freesurfer": true`` for a FreeSurfer-dependent Python function.
The function importer exposes this as **Run in FreeSurfer environment**.
It is off by default, preserving existing Python node behavior.
Functions must be importable module-level callables, not instance methods or
closures. Parameters/results cross a subprocess boundary through private,
temporary pickle files; do not pass Qt objects or rely on in-place mutation of
Python input objects. ``Path`` values are reconstructed for the receiving OS;
absolute Windows path strings in arguments are also translated.
Graphical child-process viewers (for example watershed ``show=True``) require
a working display in the execution OS.

Commands use the same inputs and parameter widgets as Python nodes, but replace
the callable with ``command`` and ``command_args``. For example::

    {
        "recon-all": {
            "command": ["recon-all"],
            "command_args": {
                "subject": "-s",
                "anat": "-i",
                "all": "-all",
                "extra_args": null
            },
            "uses_freesurfer": true,
            "bids_subject_from": "anat",
            "inputs": {
                "anat": {"accepted_ports": ["anat"], "optional": false}
            },
            "parameters": {
                "all": {"gui": "BoolGui", "default": true},
                "extra_args": {"gui": "ListGui", "default": []}
            },
            "outputs": {"subject": {"accepted_ports": ["subject"]}},
            "target": "file",
            "category": "FreeSurfer",
            "class_name": null
        }
    }

Every supplied input/parameter needs a ``command_args`` entry. ``true`` adds a
standalone flag; ``false`` and ``null`` omit it. Lists repeat a named flag for
each value. A null flag means positional tokens (useful for extra argv).
Command outputs pass through supplied arguments with matching names after
successful execution (one value or a tuple in output order); missing output
arguments raise an error before execution. ``bids_subject_from`` names an image
argument whose BIDS subject supplies ``subject`` as ``sub-<label>``.
That image is required; supplying an explicit subject raises an error.
Non-FreeSurfer commands can omit ``uses_freesurfer``.
Definitions are currently authored in plugin JSON.
Command nodes persist and reload with the graph and export to executable
Python pipelines like function nodes.

Testing without an 8 GB CI installation
---------------------------------------
The ordinary test suite uses real short Python subprocesses, a synthetic
FreeSurfer setup script on POSIX, mocked WSL invocation/path conversion,
and GUI/controller/code-generation tests. It needs no FreeSurfer download or
license. This tests argument handling, environment isolation, output draining,
failures, serialization and node persistence on GitHub-hosted CI.

Optional real integration tests are enabled with
``MNENODES_TEST_FREESURFER=1`` on a machine with FreeSurfer and its license.
They run a version query and watershed on a temporary copy of the bundled
fsaverage MRI, verify the three BEM surface files, and remove temporary data.
A manually triggered job on a self-hosted runner with a persistent FreeSurfer
installation is suitable for these tests; recon-all is deliberately excluded.
