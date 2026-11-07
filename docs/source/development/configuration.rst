Pipeline configuration versus Settings
======================================

Choose the owner
----------------

.. list-table::
   :header-rows: 1
   :widths: 25 40 35

   * - Store
     - Examples
     - Scope
   * - Controller configuration
     - Node graph, function parameters, input selections, custom groups,
       plugin metadata, coregistration subject mappings
     - The pipeline JSON; intended to travel with the workflow
   * - Settings
     - Local BIDS/output paths, recent plugin paths, disabled plugins,
       theme, fonts, console preferences
     - This device's settings JSON; not a portable pipeline definition

Ask whether a value describes the workflow or the machine running it.
Pipeline metadata may identify a dataset or plugin, but that does not make
the recording files or a device's absolute paths portable.

Persist through the owner
-------------------------

Use ``controller.get()``, ``set()``, ``set_dict_value()``, and the parameter
helpers instead of modifying ``_config`` directly. Controller writes can be
delayed; ``flush()`` persists current state, and the Save actions use it.
A mutable object returned by ``get()`` can be shared with a model: changing it
in place is not, by itself, a persistence notification. Wire the appropriate
change signal to the controller's update/flush path.

Use ``settings.get()`` and ``settings.set()`` for device values.
Settings uses typed JSON, file locking, and atomic file replacement.
``MNENODES_SETTINGS_DIR`` selects an isolated directory or a JSON file for
tests and development.

Defaults and editable preferences
---------------------------------

Pipeline defaults live in ``backend.controller.default_config``.
The packaged ``resources/settings.toml`` defines editable preferences:
defaults, widgets, descriptions, tabs, and restart behavior.
Add editable settings there instead of hard-coding another settings-dialog row.
Internal device defaults remain in ``backend.settings``.

Dataset switching and pipeline switching have explicit reset rules.
Do not clear selections or local folders incidentally during a widget refresh.
See :doc:`/documentation/settings` for the user-visible rules and
:doc:`widgets` for model reference ownership.
