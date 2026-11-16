# mne-nodes

Build MEG and EEG pipelines visually with [MNE-Python](https://mne.tools/stable/).
Connect processing nodes, set their parameters, and run them on your recordings.

!!! warning "Early development"
    mne-nodes is **not production-ready for analysis**. Validate your workflow
    and results before using them scientifically.

[![An EEG pipeline ending in a source estimate, with the console open](_static/screenshots/linux/pipeline.png)](_static/screenshots/linux/pipeline.png)

## How it works

1. **Select recordings** from a BIDS dataset.
2. **Add nodes** from plugins and **connect** them.
3. **Run** the pipeline and follow it in the console.

[Install](installation.md){ .md-button .md-button--primary }
[Build your first pipeline](documentation/pipelines.md){ .md-button }

All screenshots are generated from the application with a tiny demo dataset.
The demo analysis illustrates the interface; it is not a validated analysis.
