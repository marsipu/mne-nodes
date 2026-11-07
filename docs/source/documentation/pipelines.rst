Build and run a pipeline
========================

Choose data
-----------

1. Use **File > New Pipeline** to create a JSON pipeline file, or
   **File > Load Pipeline** to reopen one.
2. Use **Set BIDS Root** on the input node to select the folder containing
   ``dataset_description.json``. See :doc:`datasets` for required metadata.
3. Check recordings in a datatype tab, or select recording groups in **Groups**.
   Dimmed output ports are unavailable for the current selection; hover over
   them for the reason.

Add and connect nodes
---------------------

1. :doc:`Load a plugin <plugins>` to make its functions available.
2. Open **View > Node Picker** and drag a function into the canvas.
   Alternatively, right-click the canvas and choose a categorized function.
3. Drag an output port to a compatible input port. The port represents data
   passed between functions, not a filename you have to enter manually.
4. Set parameters inside each node. Use **Auto-Layout Nodes** to arrange the graph.

.. figure:: /_static/screenshots/linux/node-picker.png
   :alt: Node Picker listing the bundled example_filter function.

   The picker groups available functions by their plugin categories.

Run and save
------------

Click the input node's start button to run its downstream workflow for the
selected recordings. Starting a function node runs that node and its downstream
nodes. Inputs from upstream nodes outside that run must be readable from
saved derivatives, with a reader supplied by the plugin.

Follow progress and errors in the console. A successful run clears rerun
indicators for nodes whose configuration has not changed during execution.
Changing parameters marks affected nodes for another run.

An output-saving checkbox appears when a plugin supplies a writer. Enable it
to save that node's results; otherwise results are passed along in memory.
Use **File > Save Pipeline** (``Ctrl+S``) to persist the graph and parameters.
Saving a pipeline does not save recording data or execute its nodes.

Next: :doc:`function_importer` to create your own nodes, or :doc:`sharing`
to export a pipeline.
