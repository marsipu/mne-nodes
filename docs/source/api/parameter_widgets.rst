Parameter Widgets
=================

.. currentmodule:: mne_nodes.gui.parameter

All parameter GUI classes expose fully typed constructors to simplify
configuration and documentation. Refer to the class docstrings for the
annotated arguments.

When loading saved parameters, widgets convert between neighboring types
(``int``/``float``, ``tuple``/``list``, and ``str``/``pathlib.Path``) instead
of replacing the value with the default. Float-to-integer conversion is only
allowed for integral values (for example, ``3.0`` becomes ``3``, but ``3.5``
falls back to the default). Booleans are not converted to numeric types.
Already accepted types and optional ``None`` values are preserved.
Unrelated types and failed conversions still use the default and log a warning.
The same rules apply when switching types in a multi-type widget.

.. automodule:: mne_nodes.gui.parameter
   :no-members:
   :no-inherited-members:

.. autosummary::
   :toctree: ../generated

   Param
   BoolGui
   CallableGui
   CheckListGui
   ComboGui
   DataFrameGui
   DateTimeGui
   DictGui
   FloatGui
   IntGui
   LabelGui
   ListGui
   MultiTypeGui
   SliceGui
   SliderGui
   StringGui
   DualTupleGui
