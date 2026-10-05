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
