# Build and run a pipeline

## Choose data

1. Use **File > New Pipeline** to create a JSON pipeline file, or
   **File > Load Pipeline** to reopen one.
2. Use **Set BIDS Root** on the input node to select the folder containing
   `dataset_description.json`. See [datasets](datasets.md) for required metadata.
3. Check recordings in a datatype tab, or select recording groups in **Groups**.
   Dimmed output ports are unavailable for the current selection; hover over
   them for the reason.

## Add and connect nodes

1. [Load a plugin](plugins.md) to make its functions available.
2. Right-click the canvas and choose a function from its category menu.
   Right-clicking a port lists only functions compatible with that port.
3. Drag an output port to a compatible input port. The port represents data
   passed between functions, not a filename you have to enter manually.

   ![Dragging a connection from an output port to a compatible input port.](../_static/screenshots/linux/connect-ports.png)

4. Set parameters inside each node. Use **Auto-Layout Nodes** to arrange the graph.

## Run and save

Click the input node's start button to run its downstream workflow for the
selected recordings. Starting a function node runs that node and its downstream
nodes. Inputs from upstream nodes outside that run must be readable from
saved derivatives, with a reader supplied by the plugin.

Follow progress and errors in the console. A successful run clears rerun
indicators for nodes whose configuration has not changed during execution.
Changing parameters marks affected nodes for another run.

An output-saving checkbox appears when a plugin supplies a writer. Enable it
to save that node's results; otherwise results are passed along in memory.
Use **File > Save Pipeline** (`Ctrl+S`) to persist the graph and parameters.
Saving a pipeline does not save recording data or execute its nodes.

Next: [function importer](function_importer.md) to create your own nodes, or [sharing](sharing.md)
to export a pipeline.
