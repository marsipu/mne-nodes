CI screenshot demo
==================

These are real Qt widget captures generated from the same commit as this
documentation on Linux, Windows, and macOS. Select an operating system below;
the selection stays synchronized between the examples.

The demo uses the bundled ``example_filter`` plugin and the tiny BIDS test
dataset. It does not download recordings or execute an analysis. The light
theme, application style, font size, and window sizes are fixed; installed
fonts and Qt's platform integration can still differ between runners.

Connected pipeline
------------------

The EEG output of the input node is connected to ``example_filter``.
The filter's high-pass and low-pass parameters are visible inside its node.

.. tab-set::

   .. tab-item:: Linux
      :sync: linux

      .. figure:: /_static/screenshots/linux/pipeline.png
         :alt: Linux: EEG input connected to example_filter with its parameters.

         Connected pipeline on Linux.

   .. tab-item:: Windows
      :sync: windows

      .. figure:: /_static/screenshots/windows/pipeline.png
         :alt: Windows: EEG input connected to example_filter with its parameters.

         Connected pipeline on Windows.

   .. tab-item:: macOS
      :sync: macos

      .. figure:: /_static/screenshots/macos/pipeline.png
         :alt: macOS: EEG input connected to example_filter with its parameters.

         Connected pipeline on macOS.

Choosing a function
-------------------

Open **View > Node Picker** to browse the available functions.
Here, the bundled example plugin is loaded and ``example_filter`` is selected.

.. tab-set::

   .. tab-item:: Linux
      :sync: linux

      .. figure:: /_static/screenshots/linux/node-picker.png
         :alt: Linux: Node Picker with example_filter selected.

         Node Picker on Linux.

   .. tab-item:: Windows
      :sync: windows

      .. figure:: /_static/screenshots/windows/node-picker.png
         :alt: Windows: Node Picker with example_filter selected.

         Node Picker on Windows.

   .. tab-item:: macOS
      :sync: macos

      .. figure:: /_static/screenshots/macos/node-picker.png
         :alt: macOS: Node Picker with example_filter selected.

         Node Picker on macOS.
