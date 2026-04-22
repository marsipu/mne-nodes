# mne-nodes

## A Node-GUI for [MNE-Python](https://mne.tools/stable/index.html)
This is a GUI to facilitate offline MEG/EEG data processing with MNE-python.
To visualize the data-flow a node-based approach is used.
# ToDo: Show overview of GUI

## Installation
1. Install MNE-python as instructed in the [documentation](https://mne.tools/stable/install/index.html)
2. Open the command prompt and activate the conda-environment where you installed mne-python (or just open the command prompt when you installed mne-python with an [installer](https://mne.tools/stable/install/installers.html#installers))
3. Install **mne-nodes**:
    - Install the development version with `pip install git+https://github.com/marsipu/mne_nodes.git@main`
    - # ToDo: Add PyPi install

## Update
Run `pip install --upgrade --no-deps --force-reinstall git+https://github.com/marsipu/mne_nodes.git@main`
for an update to the development version
or `pip install --upgrade mne-nodes` for the latest stable release.

## Start
Run `mne_nodes` in your conda-environment where you installed mne-python and mne-nodes.

**or**

run \_\_main\_\_.py from the terminal or an IDE like PyCharm, VSCode, Atom,
etc.

***When using the pipeline and its functions bear in mind that the pipeline is
still in development!
The basic functions supplied are just a suggestion and you should verify before
usage if they do what you need.
They are also partly still adjusted to specific requirements which may not
apply to all data.***

## Bug-Report/Feature-Request
Please report bugs on GitHub as an [issue](https://github.com/marsipu/mne-nodes/issues).
And if you got ideas on how to improve the pipeline or some feature-requests,
you are welcome to open an [issue](https://github.com/marsipu/mne-nodes/issues) as well.

## Contribute
Contributions on bug fixes and implementation of new features are very welcome.
To implement new analysis pipelines, you should build them in a separate repository and add them as custom functions as detailed in the documentation (ToDo: Link to custom-function documentation).

Prerequisites: You need a [GitHub-Account](https://github.com/) and [git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git) installed locally.
### Development Setup
1. Fork this repository on GitHub
2. Move to the folder where you want to clone to
3. Clone **your forked repository** with git from a
   terminal: `git clone <url you get from the green clone-button from your forked repository on GitHub>`
4. Add a remote branch _upstream_ to git for
   updates from the main-branch: `git remote add upstream git://github.com/marsipu/mne-nodes.git`
5. Install your forked version including development dependencies with pip: `pip install -e .[test,docs]`
6. Install the pre-commit hooks with: `pre-commit install`

**Alternative:** You can use [mne-dev-setup](https://github.com/marsipu/mne-dev-setup) for the setup of a development environment.

### Workflow for contributing
1. Create a branch for changes: `git checkout -b <branch-name>`
2. Commit changes: `git commit -am "<your commit message>"`
3. Push changes to your forked repository on GitHub: `git push`
4. Make a new _pull request_ from your new feature branch
5. After review, your changes can be merged into the main-branch

## Acknowledgments
- This application serves as a GUI for [MNE-Python](https://mne.tools/stable/index.html)
> A. Gramfort, M. Luessi, E. Larson, D. Engemann, D. Strohmeier, C. Brodbeck, L. Parkkonen, M. Hämäläinen, MNE software for processing MEG and EEG data, NeuroImage, Volume 86, 1 February 2014, Pages 446-460, ISSN 1053-8119, [DOI](https://doi.org/10.1016/j.neuroimage.2013.10.027)
- [mne-bids](https://mne.tools/mne-bids/) is used to read and write data in BIDS format and the tiny-bids-dataset is used for testing.
- [mne-bids-pipeline](https://mne.tools/mne-bids-pipeline/) served as inspiration for the processing steps and their implementation of bids-derivatives.
- Code from [NodeGraphQt](https://github.com/jchanvfx/NodeGraphQt) was used to implement the node-gui.
- The colorpalettes for light and dark theme are inspired from [PyQtDarkTheme](https://github.com/5yutan5/PyQtDarkTheme).
- The development was supported by Code Completion and Coding Agents through GitHub Copilot (inlcuding GPT-Codex, Anthropic Sonnet).

## License

The `mne-nodes` project is licensed under the BSD\-3\-Clause license. It uses PySide6, which is licensed under the LGPL. When using [`qtpy`](https://github.com/spyder-ide/qtpy) with alternative Qt backends (e.g. PyQt6), the applicable licensing obligations are determined by the chosen backend.
