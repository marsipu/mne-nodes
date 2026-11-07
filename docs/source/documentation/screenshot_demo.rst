:orphan:

CI screenshot demo
==================

These are real Qt widget captures generated on Ubuntu from the same commit as
this documentation.

The demo uses the bundled ``example_filter`` plugin and the tiny BIDS test
dataset. It does not download recordings or execute an analysis. The light
theme, application style, font size, and window sizes are fixed; installed
fonts and Qt's platform integration can still differ between runners.

Connected pipeline
------------------

The workflow filters EEG, creates epochs, and branches into averaging,
covariance, and a spherical forward model before estimating sources.
Its console shows the completed run. The synthetic sensor positions and model
are illustrative, not a validated source analysis. For the main guides, see
:doc:`pipelines`, :doc:`function_importer`, and :doc:`coregistration`.

.. figure:: /_static/screenshots/linux/pipeline.png
   :alt: Branched source-analysis workflow with a completed console.

   Connected pipeline.

Choosing a function
-------------------

Open **View > Node Picker** to browse the available functions.
Here, the bundled example plugin is loaded and ``example_filter`` is selected.

.. figure:: /_static/screenshots/linux/node-picker.png
   :alt: Node Picker with example_filter selected.

   Node Picker.
