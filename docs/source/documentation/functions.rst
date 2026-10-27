Functions
=========
Function names must be always unique.

Node placement and auto-layout
------------------------------
Right-click a port to add and connect a compatible function. New upstream nodes
are placed to the left of input ports; downstream nodes are placed to the right
of output ports. Connected ports are vertically aligned where space permits,
and overlapping nodes are moved down. Nodes added without a position or a
connection are placed at the center of the current view.

Adding nodes does not pan or zoom the view. Use the view's fit or center actions
when you want to frame the graph.

Choose **View > Auto-Layout Nodes** (``Ctrl+L``) to arrange the graph.
The same action is available by right-clicking the viewer background.
Auto-layout arranges nodes from left to right with the default horizontal and
vertical gaps, using the actual node sizes. Nodes are placed in the layer that
keeps their pipes short, and pipes spanning several layers reserve a channel
through the layers in between. Within each layer, nodes are ordered to reduce
pipe crossings and then placed vertically to minimize the vertical distance
between connected ports. This is a heuristic, not a guarantee of a globally
optimal or obstruction-free layout. Auto-layout preserves the graph center and
does not change the view; laying out a subset leaves other nodes fixed.

Choose the pipe style under **View > Pipe Style**: *Curved*, *Straight*,
*Angled*, or *Routed Around Nodes*. Routed pipes use horizontal and vertical
segments that go around other nodes instead of behind them. Parallel routed pipes
that share a channel are spread apart by a small pipe padding
(``defaults["pipes"]["padding"]`` in ``node_defaults.py``), so each pipe stays
distinguishable and clickable. While nodes are dragged, routed pipes keep their
shape (or show a simple angled preview) and are re-routed when the mouse is
released. The chosen style is remembered between sessions.

Parameters
==========
Parameters are stored per function, thus parameters with the same name can exist in different functions with different values.
The parameters are configured per function.

Parameter Names
---------------
While parameters of different functions can have the same name, parameter names within a function must be unique.

Set a parameter to None
-----------------------
To set a parameter to None, uncheck the checkbox next to the parameter name. To allow this, *none_select* has to be set to ``True`` in the parameter configuration.
