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

Each export asks whether to include rich-formatted progress output. **Plain
output** is selected by default and omits the progress-formatting imports,
frames, and timing wrappers while retaining output from the pipeline functions.
Choose **Rich output** to include recording and function frames, load/save
announcements, and execution timings. Canceling this choice writes no export.
The choice also applies to the script inside a complete-project archive.
Pipeline runs inside the application continue to use rich-formatted output.
