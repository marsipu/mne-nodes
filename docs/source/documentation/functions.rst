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
vertical gaps, using the actual node sizes. It refines the order and vertical
alignment of each layer to favor pipes that do not pass through unrelated nodes,
then shorter total pipe length. This is a bounded heuristic, not a guarantee of
a globally optimal or obstruction-free layout. Auto-layout preserves the graph
center and does not change the view; laying out a subset leaves other nodes fixed.

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
