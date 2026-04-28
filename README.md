[![CIs](https://github.com/marsipu/mne-nodes/actions/workflows/run_tests.yml/badge.svg)](https://github.com/marsipu/mne-nodes/actions/workflows/run_tests.yml)

[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/marsipu/mne-nodes/main.svg)](https://results.pre-commit.ci/latest/github/marsipu/mne-nodes/main)

# mne-nodes
![Overview](https://raw.githubusercontent.com/marsipu/mne-nodes/main/mne_nodes/extra/wip_overview.png "Overview of the mne-nodes GUI")

# !!! This application is still in early development and not production-ready for real-world analysis !!!

## A Node-GUI for [MNE-Python](https://mne.tools/stable/index.html)
This is a GUI to facilitate offline MEG/EEG data processing with MNE-python.
To visualize the data-flow a node-based approach is used.

## Installation
1. Install MNE-python as instructed in the [documentation](https://mne.tools/stable/install/index.html)
2. Open the command prompt and activate the conda-environment where you installed mne-python (or just open the command prompt when you installed mne-python with an [installer](https://mne.tools/stable/install/installers.html#installers))
3. Install **mne-nodes**:
    - Install the latest release with `pip install mne-nodes`

   or

    - Install the development version with `pip install git+https://github.com/marsipu/mne-nodes.git@main`


## Update
Run `pip install --upgrade --no-deps --force-reinstall git+https://github.com/marsipu/mne-nodes.git@main`
for an update to the development version
or `pip install --upgrade mne-nodes` for the latest release.

## Start
Run `mne_nodes` in the terminal of your conda-environment where you installed mne-python and mne-nodes

**or**

run \_\_main\_\_.py from the terminal or an IDE like PyCharm, VSCode, Atom,
etc.


## Bug-Report/Feature-Request
Please report bugs on GitHub as an [issue](https://github.com/marsipu/mne-nodes/issues/new?template=bug_report.yml).
And if you got ideas on how to improve the pipeline or some feature-requests,
you are welcome to open an [issue](https://github.com/marsipu/mne-nodes/issues/new?template=feature_request.yml) as well.

## Contribute
Contributions on bug fixes and implementation of new features are very welcome.
Have a look at the [contributing guidelines](CONTRIBUTING.md) for more information on how to contribute.

## Acknowledgments
- This application serves as a GUI for [MNE-Python](https://mne.tools/stable/index.html)
> A. Gramfort, M. Luessi, E. Larson, D. Engemann, D. Strohmeier, C. Brodbeck, L. Parkkonen, M. Hämäläinen, MNE software for processing MEG and EEG data, NeuroImage, Volume 86, 1 February 2014, Pages 446-460, ISSN 1053-8119, [DOI](https://doi.org/10.1016/j.neuroimage.2013.10.027)
- [mne-bids](https://mne.tools/mne-bids/) is used to read and write data in BIDS format and the tiny-bids-dataset is used for testing.
- [mne-bids-pipeline](https://mne.tools/mne-bids-pipeline/) served as inspiration for the processing steps and their implementation of bids-derivatives.
- Code from [NodeGraphQt](https://github.com/jchanvfx/NodeGraphQt) was used to implement the node-gui.
- The colorpalettes for light and dark theme are inspired from [PyQtDarkTheme](https://github.com/5yutan5/PyQtDarkTheme).
- The development was supported by Code Completion and Coding Agents (e.g. GitHub Copilot)

## License
The `mne-nodes` project is licensed under the [BSD\-3\-Clause license](LICENSE). It uses PySide6, which is licensed under the LGPL. When using [`qtpy`](https://github.com/spyder-ide/qtpy) with alternative Qt backends (e.g. PyQt6), the applicable licensing obligations are determined by the chosen backend.
