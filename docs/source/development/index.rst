Development
===========

.. toctree::
    :maxdepth: 2

    Docker GUI <docker_gui>

Test isolation
--------------

Run tests in the existing development environment, for example
``conda run -n mnedev pytest mne_nodes/tests/test_main_window.py``.
Pytest redirects ``MNENODES_SETTINGS_DIR`` to temporary settings before
collecting test modules, and gives each test its own fresh settings directory,
even when it does not request the ``settings`` fixture. Test logging also uses
temporary files. The original environment is restored when pytest finishes.

Tests must not persist demo pipelines, plugin selections or dataset paths into
the settings used by normal application startup. Subprocesses should inherit
the isolated environment, or explicitly select their own temporary settings
directory. Use ``monkeypatch.setenv`` rather than assigning environment
variables directly in tests so overrides are restored during teardown.

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
