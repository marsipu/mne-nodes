
# CI screenshot demo

These are real Qt widget captures generated on Ubuntu from the same commit as
this documentation.

The demo uses the bundled `example_filter` plugin and the tiny BIDS test
dataset. It runs the illustrative analysis without downloading recordings. The light
theme, application style, font size, and window sizes are fixed; installed
fonts and Qt's platform integration can still differ between runners.

## Connected pipeline

The workflow filters EEG, creates epochs, and branches into averaging,
covariance, and a spherical forward model before estimating sources.
Its console shows the completed run. The synthetic sensor positions and model
are illustrative, not a validated source analysis. For the main guides, see
[pipelines](pipelines.md), [function importer](function_importer.md), and [coregistration](coregistration.md).

![Branched source-analysis workflow with a completed console.](../_static/screenshots/linux/pipeline.png)

Connected pipeline.

## Connecting ports

Drag from an output port to a compatible input port to connect two nodes.

![Dragging a connection from an output port to a compatible input port.](../_static/screenshots/linux/connect-ports.png)

Connecting ports.
