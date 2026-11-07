# Core modules

## Application and state

`mne_nodes.__main__` starts the installed application and initializes Qt.
`backend.controller.Controller` coordinates the active pipeline, dataset
paths, plugin loading, metadata, and execution. It is not a widget.
`backend.settings.Settings` persists device preferences independently of
the pipeline; see [configuration](configuration.md).
Older plugins importing `mne_nodes.pipeline` must use `mne_nodes.backend`.
The application entry point and `mne_nodes.gui` namespace are unchanged.

`gui.main_window.MainWindow` wires menus, the node viewer, and the console.
`gui.node.node_viewer.NodeViewer` owns the scene's nodes and connections,
serializes the graph, and determines the selected execution sequence.
`gui.node.function_node.FunctionNode` constructs ports and parameter widgets
from plugin metadata.

## From graph to execution

1. The viewer builds an ordered node sequence for the selected start nodes
   and their downstream dependencies.
2. `backend.code_generation.CodeGenerator` converts that sequence into Python,
   including data loading, function calls, and configured output writing.
3. The controller starts the generated script in a separate process.
   `gui.console` displays streamed output and progress.
4. `backend.execution` also provides workers for background GUI operations;
   their signals report results, errors, progress, and cooperative cancellation.

Keep long-running work out of the GUI thread. GUI workers and pipeline
subprocesses are distinct mechanisms; do not treat a worker as a Qt widget or
assume an in-process object is available in a child process.

## Data and extension boundaries

`backend.io` handles typed JSON and data I/O. `backend.data_import` prepares
sample BIDS data. `backend.coregistration` discovers digitization groups,
fits transformations, and saves them; `gui.dialogs.coreg_dialog` manages
interaction and the manual MNE window.

`backend.function_parser` and `gui.function_widgets` interpret Python
functions and configure their node definitions. `backend.package_utils`
handles package discovery and installation. Plugin source and metadata belong
to the plugin, not to the node widgets.

Shared UI mechanisms live in `gui.parameter`, `gui.widgets`,
`gui.widget_models`, `gui.widget_registry`, and `gui.colors`.
Reuse these rather than introducing parallel state or styling systems.
See [widgets](widgets.md), [plugin format](plugin_format.md), and [internals](internals.md).
