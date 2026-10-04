Development
===========

.. toctree::
    :maxdepth: 2

    Docker GUI <docker_gui>

Widget Registry
---------------

GUI widgets are discovered through a registry stored on the current
``QApplication``. Importing the registry does not import the main window or
node viewer. Lookups return ``None`` when no application or entry exists.

.. code-block:: python

    from mne_nodes.gui.widget_registry import get_widget, widget_registry

    widget_registry().register("my_dialog", dialog, retain=True)
    main_window = get_widget("main_window")
    widget_registry().unregister("my_dialog", dialog)

Registration uses weak references by default. Use ``retain=True`` when the
registry should keep a parentless widget's Python wrapper alive. Qt destruction
automatically removes an entry, including retained entries. Unregister widgets
on close when they should no longer be discoverable even if Qt has not deleted
them. Passing the widget to ``unregister`` prevents cleanup of an older instance
from removing its replacement. Closing a widget does not automatically destroy
it unless its Qt deletion policy requests that behavior.

The controller exposes typed ``main_window`` and ``viewer`` properties backed
by this registry. ``viewer`` returns ``None`` when unavailable; ``main_window``
raises ``RuntimeError``. The former package-global ``_widgets`` dictionary has
been replaced by this API.

Interactive Welcome Tour
------------------------

``WelcomeTour`` accepts static widgets or graphics items, as before. For targets
that do not yet exist, pass a zero-argument callable as ``widget``. Return
``None`` while waiting, rather than indexing a missing node. The tour rechecks
the callable every 100 ms and follows the returned object when it becomes
available. Resolve from the current viewer state so removed or replaced nodes
are not retained.
The tour only moves its floating panel; it does not zoom or pan the node viewer.
The panel is anchored beside the target with a gap, preferring left/right when
it fits, otherwise above/below. It is aligned with the target and clamped inside
the application boundaries. If no side has enough space, the panel uses the
best available region, with an in-window overlapping fallback for large targets.
The panel paints an opaque, palette-based background so text remains readable
when this fallback overlaps the node graph.
Node layout and view fitting remain under the viewer's normal behavior.

An optional ``is_complete`` callable checks whether the user has completed a
task. Keep these queries cheap and free of side effects. Next is visibly dimmed
and disabled until the target exists and the check succeeds. Success displays
feedback, emits ``task_completed(index)`` and automatically advances on the next
event-loop turn, after the current GUI action finishes. Completion is rechecked
before advancing, so undoing the action can cancel the transition. Signal-driven
tasks (``requires_completion=True`` with ``complete_task(index)``) also advance
automatically. Informational steps still require Next.

Widgets accepting input must be listed in ``interactive_widgets``. That widget
and its child controls remain enabled; other interactive widgets and menu/toolbar
controls are disabled for the step. This includes widgets embedded in graphics
proxies, which may not belong to the main window's QObject tree. The input-file
checklists and their viewports are enabled during the file-selection task.
``interactive_views`` keeps a graphics view
and its viewport active for canvas tasks without enabling embedded controls
elsewhere in the view. In that case, set ``interactive_items`` to the specific
scene items the user must interact with; mouse input elsewhere on the canvas is
blocked. Right-clicks, context menus (including their submenus) and hover
movement in an interactive view always pass through, and
during an active drag, movement and release are allowed so gestures such as
connecting ports can complete. Native window releases pass through to Qt before
filtering their widget recipients, including allowed embedded checkbox controls.
Keyboard input is accepted only by the tour
widget or explicitly enabled targets, and shortcuts are suppressed unless the
current target has focus. Original enabled states are restored when the tour
ends. Next (labelled Finished on the last step) and Cancel both discard the demo
and prompt for a new or existing user pipeline. Cancel remains available during
incomplete tasks. Closing the main window cancels the tour without prompting
for a new pipeline.

The built-in tour lives in ``mne_nodes.gui.welcome_tour``:
``build_welcome_steps(ct, main_window)`` defines the steps and
``start_welcome_tour(ct, main_window)`` asks the user, loads a temporary copy of
the packaged ``Welcome_pipeline.json`` and returns the tour. The temporary copy
is deleted when the tour ends. The packaged ``example_function`` plugin and its
configuration are loaded into the tour's session without registering it in
device settings. Finish, Cancel and window close unload its functions and nodes;
any plugin/function definitions already present before the tour are restored.
The controller applies the loaded configuration before constructing its nodes,
so input checklists use that pipeline's selections, not the previous pipeline's.
The parameter task enables the function node's parameter panel and advances when
any parameter differs from its default (for example, changing ``lowpass`` from
30 to 40). Processing starts from the input node's start button.
The start task waits for the console dock's ``process_started`` signal before
advancing to the console explanation; a click or merely opening the dock does
not complete it. The final step hides the dimming overlay to show the entire
application. Going Back restores the overlay for earlier steps.
``Controller.initialize_welcome_tour`` only calls
these and resets the pipeline afterwards.

.. code-block:: python

    from mne_nodes.gui.welcome_tour import WelcomeTour

    def function_node():
        return next(iter(viewer.function_nodes.values()), None)

    def connected():
        node = function_node()
        return node is not None and any(
            port.node is viewer.input_node
            for input_port in node.inputs
            for port in input_port.connected_ports
        )

    tour = WelcomeTour(main_window, [
        {
            "widget": viewer,
            "text": "Create a function node.",
            "is_complete": lambda: function_node() is not None,
        },
        {
            "widget": function_node,
            "text": "Connect the input node to your function node.",
            "is_complete": connected,
        },
    ])
    tour.task_completed.connect(lambda index: print(f"Completed step {index}"))

For actions reported by a Qt signal rather than inspectable state, set
``requires_completion=True`` and connect that signal to
``lambda: tour.complete_task(step_index)``. The explicit index prevents delayed
feedback from completing the wrong step. Completion is remembered when
revisiting that step; use a predicate instead for reversible state.

The built-in tour includes a file-selection step before the function node's
start button. It highlights the input-node widget and waits until at least one
file is checked in a datatype tab. This mirrors the controller's existing
start-button enablement rule.

Missing targets display waiting feedback with no highlight. Embedded widgets
such as parameter boxes and start buttons are highlighted through their
graphics proxies. Back and Finish remain available while waiting. Finishing
stops the timer and removes observers before notifying the controller, which
discards the temporary demo pipeline and prompts for a user pipeline.
Creating a function node also refits the viewer to include the complete graph,
so nodes created at an off-screen position remain visible.
