Development
===========

.. toctree::
    :maxdepth: 2

    Docker GUI <docker_gui>

Project layout
--------------

Install the checkout with ``pip install -e ".[test,docs]"`` before running
the application, tests or Sphinx. Launch the application with
``python -m mne_nodes``; no import-path modifications are needed.

The installed package lives in ``src/mne_nodes`` with Qt components in ``gui``,
workflow services in ``backend`` and bundled assets in ``resources``.
Tests and their datasets live in the root ``tests`` directory. Development
helpers live in the root ``development`` directory and can be run as modules,
for example ``python -m development.param_tester``. Neither directory is
included in the wheel.

Plugins using the previous ``mne_nodes.pipeline`` imports must switch to
``mne_nodes.backend``. The ``mne_nodes.gui`` module path and application
entry point are unchanged.

MNE port aliases
----------------

``development/_generate_mne_config.py`` derives accepted port names from MNE
class names and documented parameter names. Add naming mismatches that cannot
be inferred from classes to ``hard_aliases``, listing both directions (for
example, ``surfs`` and ``surfaces``). These aliases are included for inputs,
outputs and I/O matching. A matching container parameter is treated as a node
input, but primitive parameters such as booleans remain editable parameters.
Regenerate the plugin configs to apply alias changes to the application.

Subject-only execution
----------------------

The code generator tracks subject-only values separately from loaded values.
Loading ``subject`` from a recording starts that dependency chain. A non-method
node with outputs joins the chain only when all its supplied inputs are
subject-only; its outputs then propagate that property. Disk-loaded derivatives
are not assumed to be subject-only. Recording inputs such as ``info`` or
``trans`` break the chain.
Passing an object to a non-shared node also ends its subject-only provenance:
that node may modify it in place. Other live objects may alias the mutated
inputs, so their provenance is conservatively cleared too. The immutable
resolved subject name is exempt.

Generated scripts keep a run-local cache keyed by execution target, node name
and resolved FreeSurfer subject. Distinct nodes therefore keep their own
parameters, while different recordings or groups using the same reconstruction
reuse a node's result. Outputs and live subject-only values are deep-copied
together so cache hits restore in-place changes and aliases made by the shared
node, while downstream changes cannot mutate the cache.
Saving stays outside the computation cache,
preserving the current derivative I/O behavior. No persistent cache is added.

Semantic colors
---------------

``mne_nodes.gui.colors`` is the application-wide registry for semantic colors.
``CATEGORY_COLORS`` stores the MNE-logo-derived HEX palette, and
``CATEGORY_DATATYPES`` assigns known datatype names and aliases to categories.
``DATATYPE_CATEGORIES`` is derived from those assignments. Add new type names to
the category membership rather than duplicating colors in individual widgets.

Use ``datatype_color(name, accepted_datatypes)`` to resolve a color. An explicit
known name wins; otherwise accepted aliases must agree on one category.
Unknown or mixed-category outputs retain the consumer's default styling.
Output ports and input-node datatype tabs use this API; future node and parameter
coloring should reuse it. Larger widgets should use restrained accents rather
than saturated backgrounds. ``ACCENT_OPACITY`` and ``ACTIVE_ACCENT_OPACITY`` in
the same registry control the translucent tab underlines. The active page frame
uses ``ACCENT_OPACITY`` for a matching border; native labels and backgrounds are
preserved. Normal, connected and hovered outputs retain their
semantic color.
Disabled outputs are dimmed, while temporary connection-compatibility highlights
keep their existing meaning.

Test isolation
--------------

Run tests in the existing development environment, for example
``conda run -n mnedev pytest tests/test_main_window.py``.
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
