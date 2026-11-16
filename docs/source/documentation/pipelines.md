# Build and run a pipeline

A pipeline is a graph. Recordings enter at the input node on the left and flow
through the function nodes you connect to it.

## 1. Select recordings

Create a pipeline file with **File > New Pipeline**. On the input node, click
**Set BIDS Root**, choose your BIDS dataset, and check the recordings to process.

![The input node with the dataset button and the list of recordings](../_static/screenshots/linux/select-recordings.png)

No data at hand? **BIDS > Add Sample BIDS Data** downloads an example.
See [Datasets and recordings](data.md) for details.

## 2. Add nodes

Right-click the canvas and pick a function. The functions come from
[plugins](plugins.md).

![The canvas menu listing the functions of each plugin](../_static/screenshots/linux/add-node.png)

## 3. Connect nodes

Drag from an output port to an input port. Compatible ports are highlighted
while you drag.

![A connection being dragged between two ports](../_static/screenshots/linux/connect-ports.png)

Faster: right-click a port to add a compatible function that is connected
right away.

![The menu of an output port listing compatible functions](../_static/screenshots/linux/port-menu.png)

## 4. Set parameters

Edit parameters directly in the node. A changed parameter gets an orange frame,
and the node and everything after it are outlined until they have run again.

![A changed parameter with an orange frame](../_static/screenshots/linux/parameters.png)

## 5. Run

Click the start button of the input node. The console shows progress and
errors; press `C` to show or hide it.

![The start button and the console after a finished run](../_static/screenshots/linux/run-pipeline.png)

To run only a part, select nodes, right-click the canvas, and choose
**Start selected nodes**. These nodes and everything after them run. Results
they need from earlier nodes must have been [saved](derivatives.md).

![The canvas menu with Start selected nodes](../_static/screenshots/linux/start-selected.png)

## 6. Save

**File > Save Pipeline** (`Ctrl+S`) stores the graph and its parameters. It
does not store data: results are written only for nodes with **Save** checked,
see [Save results](derivatives.md).

!!! tip
    **View > Auto-Layout Nodes** (`Ctrl+L`) arranges the graph for you.

Next: [create your own nodes](function_importer.md) or
[share the pipeline](sharing.md).
