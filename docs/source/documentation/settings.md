# Settings

Open **Settings** to change the theme, style, font, startup window size, node
pipe style, and console wrapping. Appearance and startup size changes require a
restart; pipe style and wrapping apply immediately.

Under **Settings > Keep Plots Open**, choose whether plot windows remain open
after a pipeline finishes.

## Dataset and output folders

* **BIDS > Set BIDS root...** selects the dataset. Changing datasets clears
  selections, groups, subject mappings, and output-folder settings; it does not
  move or delete files.
* **BIDS > Derivative storage...** selects where processing results are saved.
  See [derivatives](derivatives.md).
* **BIDS > FreeSurfer subjects directory...** selects the location of
  reconstructions. See [subjects](subjects.md).

When opening another pipeline, choose whether to keep the current BIDS root.
Check the selected output location before running the pipeline.
