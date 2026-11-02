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

The EEG output of the input node is connected to ``example_filter``.
The filter's high-pass and low-pass parameters are visible inside its node.

.. figure:: /_static/screenshots/linux/pipeline.png
   :alt: EEG input connected to example_filter with its parameters.

   Connected pipeline.

Choosing a function
-------------------

Open **View > Node Picker** to browse the available functions.
Here, the bundled example plugin is loaded and ``example_filter`` is selected.

.. figure:: /_static/screenshots/linux/node-picker.png
   :alt: Node Picker with example_filter selected.

   Node Picker.
