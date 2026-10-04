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

An optional ``is_complete`` callable checks whether the user has completed a
task. Keep these queries cheap and free of side effects. Next is disabled until
the target exists and the check succeeds. Success displays feedback and emits
``task_completed(index)``; it does not automatically advance. If the user undoes
the action, the check disables Next again.

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

Missing targets display waiting feedback with no highlight. Embedded widgets
such as parameter boxes and start buttons are highlighted through their
graphics proxies. Back and Finish remain available while waiting. Finishing
stops the timer and removes observers before notifying the controller, which
discards the temporary demo pipeline and prompts for a user pipeline.
