# mne-nodes

Build MEG and EEG pipelines visually with [MNE-Python](https://mne.tools/stable/).
Connect processing nodes, set their parameters, and run them on your recordings.

!!! warning "Early development"
    mne-nodes is **not production-ready for analysis**. Validate your workflow
    and results before using them scientifically.

[![An EEG pipeline ending in a source estimate, with the console open](_static/screenshots/linux/pipeline.png)](_static/screenshots/linux/pipeline.png)

## Features

- a graphical representation of your processing pipeline.
- simple addition of processing nodes by processing python functions directly.
- run everything from within the application or
- export the pipeline as code

[Install](installation.md){ .md-button .md-button--primary }
[Build your first pipeline](user-guide/pipelines.md){ .md-button }
