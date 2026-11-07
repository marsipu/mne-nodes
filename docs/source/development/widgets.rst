Widgets, references, and lifetime
=================================

Model-backed Base widgets
-------------------------

``gui.widgets.base.Base`` combines a model, a view, and value-oriented signals:
``currentChanged``, ``selectionChanged``, and ``dataChanged``.
Specialized list, dictionary, tree, and table widgets reuse this structure.

Models can retain the original mutable data rather than copying it.
For example, ``BaseListModel(data=items)`` stores the supplied list as
``_data``; editing its rows changes that same list. This is intentional.

.. code-block:: python

   from mne_nodes.gui.widgets.list_widgets import SimpleList

   items = ["first", "second"]
   widget = SimpleList(data=items)
   items.append("third")
   widget.content_changed()

Use ``content_changed()`` to notify the view after an external in-place change.
Use ``replace_data(new_data)`` when switching the model to a different object.
Replacing a caller's variable alone does not update the model's reference.
These methods refresh the model/view; they do not automatically save a pipeline.
Connect signals to the owning service when persistence is required.

Parameter widgets
-----------------

``gui.parameter.Param`` binds a value to a dictionary, Settings, or Controller.
Controller-backed widgets require a ``function_name``; use the actual node name,
including its disambiguating suffix, so duplicate nodes keep separate parameters.

Set ``value`` or call ``set_param()`` to refresh the GUI, persist through the
data source, and emit ``paramChanged``. Subclasses provide the widget-specific
get/set hooks and ``data_type``. Reuse the base None-selection behavior rather
than adding a competing checkbox implementation.

Registry and Qt ownership
-------------------------

Find shared widgets through the application-scoped registry:

.. code-block:: python

   from mne_nodes.gui.widget_registry import get_widget, widget_registry

   main_window = get_widget("main_window")
   widget_registry().register("my_dialog", dialog, retain=True)
   widget_registry().unregister("my_dialog", dialog)

Lookups can return ``None`` before GUI initialization or after cleanup.
Registration uses weak references by default; ``retain=True`` keeps a
parentless widget's Python wrapper alive. Qt destruction removes entries.
Closing a widget is not necessarily destruction: unregister it on close when
it must no longer be discoverable. Pass the widget to ``unregister`` so an old
instance cannot remove its replacement.
The Controller's typed ``viewer`` accessor returns ``None`` when unavailable;
``main_window`` raises ``RuntimeError``. The registry module does not import
the main window or viewer.

Parent widgets where appropriate and keep workers/manual windows alive until
their operations finish. Do not restore the former package-global widget map.
See :doc:`contributing` for isolated GUI tests.
