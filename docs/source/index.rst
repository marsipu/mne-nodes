:html_theme.sidebar_secondary.remove:

mne-nodes
=========

Build MEG and EEG workflows visually with MNE-Python.
Connect processing nodes, adjust their parameters, and follow the flow of data
from recordings to results. Processing functions live in extensible plugins.

.. warning::

   mne-nodes is in early development and is **not production-ready for analysis**.
   Inspect and validate your workflow and results before using them scientifically.

.. figure:: /_static/screenshots/linux/pipeline.png
   :alt: Branched EEG workflow ending in a source estimate, with the console open.
   :target: _static/screenshots/linux/pipeline.png

.. grid:: 1 1 3 3
   :gutter: 3

   .. grid-item-card:: Install
      :link: install/index
      :link-type: doc

      Set up your environment and launch the application.

   .. grid-item-card:: Usage
      :link: documentation/index
      :link-type: doc

      Build pipelines, import functions, share plugins, and coregister recordings.

   .. grid-item-card:: Developers
      :link: development/index
      :link-type: doc

      Understand state, widgets, execution, and contributor standards.

.. toctree::
   :hidden:
   :maxdepth: 2

   Install <install/index>
   Usage <documentation/index>
   Developers <development/index>
