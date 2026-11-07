Documentation
=============

.. toctree::
   :maxdepth: 1

   datasets
   coregistration
   freesurfer
   settings

Exporting pipelines
-------------------

The **File** menu can export a Python script, a Jupyter notebook (``.ipynb``),
or a complete project ZIP archive.

New pipeline files, **Save As**, and exports use a single **Save As** dialog:
enter a filename and choose its folder in the same dialog. The appropriate
extension (``.json``, ``.py``, ``.ipynb``, or ``.zip``) is added if omitted.
New pipelines take their initial name from the filename; saving an existing
pipeline under another filename keeps its pipeline name.

Each export asks whether to include rich-formatted progress output. **Plain
output** is selected by default and omits the progress-formatting imports,
frames, and timing wrappers while retaining output from the pipeline functions.
Choose **Rich output** to include recording and function frames, load/save
announcements, and execution timings. Canceling this choice writes no export.
The choice also applies to the script inside a complete-project archive.
Pipeline runs inside the application continue to use rich-formatted output.

Error reporting
---------------

The error dialog offers **Copy traceback** to copy the original, unredacted
traceback as plain text.

**Open GitHub issue…** opens an editable report preview. The unchecked diagnostic
option adds MNE system information, loaded plugins and dataset selection counts.
Custom plugins are anonymized; dataset names, paths and subject identifiers are
not collected. System-information collection does not check for updates.

Reports redact local usernames, hostnames, filesystem paths, email addresses,
IPv4 addresses and URLs. Automatic redaction cannot recognize every private
detail in exception messages or source code; relative filenames and other
identifiers may remain. Review and edit the preview before sharing it.

Confirming the preview opens a draft in the mne-nodes GitHub repository and
copies the reviewed report to the clipboard. Nothing is submitted automatically.
If the report is too long to prefill the issue, paste it from the clipboard.
Cancelling the preview does not open a browser or change the clipboard.
