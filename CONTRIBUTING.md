# Contributing to mne-nodes

_**Contributions are very welcome! Thank you for taking the time to contribute to mne-nodes.**_

## Scope
mne-nodes is supposed to be a **GUI framework** for building and running MEG/EEG workflows.
It should not contain any analysis logic (core-functions being the exception during early development).
All analysis logic should be implemented in separate, importable Python modules/packages and maintained in their own repositories (for example on GitHub).

## Development Setup
1. Fork this repository on GitHub
2. Move to the folder where you want to clone to
3. Clone **your forked repository** with git from a
   terminal: `git clone <url you get from the green clone-button from your forked repository on GitHub>`
4. Add a remote branch _upstream_ to git for
   updates from the main-branch: `git remote add upstream git://github.com/marsipu/mne-nodes.git`
5. Install your forked version including development dependencies with pip: `pip install -e .[test,docs]`
6. Install the pre-commit hooks with: `pre-commit install`

**Alternative:** You can also use [mne-dev-setup](https://github.com/marsipu/mne-dev-setup) for the setup of a development environment.

## Workflow for contributing
1. Create a branch for changes: `git checkout -b <branch-name>`
2. Commit changes: `git commit -am "<your commit message>"`
3. Push changes to your forked repository on GitHub: `git push`
4. Make a new _pull request_ from your new feature branch
5. After review, your changes can be merged into the main-branch
