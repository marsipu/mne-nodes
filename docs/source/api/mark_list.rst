Marked lists
============

``MarkList`` replaces ``CheckDictList``. Pass a single dictionary whose keys
are the displayed items and whose values are string or boolean marks. Items
retain dictionary insertion order; selecting an item returns its key.

.. code-block:: python

   from mne_nodes.gui.widgets import MarkList

   items = {"subject-01": "ready", "subject-02": "pending"}
   widget = MarkList(
       items,
       mark_icons={
           "ready": "SP_DialogApplyButton",
           "pending": "SP_BrowserReload",
       },
   )
   items["subject-02"] = "ready"
   widget.content_changed()

Icon mappings accept ``QIcon`` objects or names from
``QStyle.StandardPixmap``. Without an explicit mapping, ``True`` uses
``SP_DialogApplyButton`` and ``False`` uses ``SP_DialogCancelButton``.
Subclasses may override the class-level ``mark_icons`` dictionary.
Unmapped marks have no icon; an empty mapping disables all icons.

The data dictionary is retained by reference. Call ``content_changed()`` after
external changes, or ``replace_data(new_dict)`` to replace it (including with
an empty dictionary). Other data types or mark values raise ``TypeError``;
unknown standard icon names raise ``ValueError``.

To migrate the old membership-based API, replace
``CheckDictList(items, assignments)`` with
``MarkList({item: item in assignments for item in items})``. Refresh that
dictionary after assignments change. The editable ``CheckDictEditList`` is
unchanged.

.. autoclass:: mne_nodes.gui.widgets.MarkList
   :members: replace_data, content_changed
