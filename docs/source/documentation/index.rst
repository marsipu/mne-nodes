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

The **File** menu can export a Python script, a Jupyter-compatible Python script
with cell markers, or a complete project ZIP archive.

New pipeline files, **Save As**, and exports use a single **Save As** dialog:
enter a filename and choose its folder in the same dialog. The appropriate
extension (``.json``, ``.py``, or ``.zip``) is added if omitted. New pipelines
take their initial name from the filename; saving an existing pipeline under
another filename keeps its pipeline name.

Each export asks whether to include rich-formatted progress output. **Plain
output** is selected by default and omits the progress-formatting imports,
frames, and timing wrappers while retaining output from the pipeline functions.
Choose **Rich output** to include recording and function frames, load/save
announcements, and execution timings. Canceling this choice writes no export.
The choice also applies to the script inside a complete-project archive.
Pipeline runs inside the application continue to use rich-formatted output.
