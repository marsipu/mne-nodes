Install and launch
==================

Use Python 3.11 or newer in an environment with a working graphical
MNE-Python installation. Follow the `MNE installation guide
<https://mne.tools/stable/install/index.html>`_ first, then activate that
environment in a terminal.

Install a release
-----------------

.. code-block:: console

   python -m pip install mne-nodes

To opt into alpha, beta, or release-candidate versions:

.. code-block:: console

   python -m pip install --upgrade --pre mne-nodes

Processing functions are provided by plugins; see
:doc:`/documentation/plugins` to load them.

Launch
------

From the same environment, run either command:

.. code-block:: console

   mne_nodes
   python -m mne_nodes

On first launch, create or choose a pipeline file and select a BIDS dataset.
The welcome tour can prepare sample data; this may download a large MNE dataset.
You can restart it with **Help > Restart Welcome Tour**.
Continue with :doc:`/documentation/pipelines`.

Update or develop
-----------------

Update a release with ``python -m pip install --upgrade mne-nodes``.
To install the development version:

.. code-block:: console

   python -m pip install git+https://github.com/marsipu/mne-nodes.git@main

For an editable checkout, follow :doc:`/development/contributing`.
