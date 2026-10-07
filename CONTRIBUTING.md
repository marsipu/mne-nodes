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
   updates from the main-branch: `git remote add upstream https://github.com/marsipu/mne-nodes.git`
5. Install your forked version including development dependencies with pip: `pip install -e .[test,docs]`
6. Install the pre-commit hooks with: `pre-commit install`

**Alternative:** You can also use [mne-dev-setup](https://github.com/marsipu/mne-dev-setup) for the setup of a development environment.

## Project layout and testing

- `src/mne_nodes/gui/`: Qt UI components.
- `src/mne_nodes/backend/`: workflow control, execution, I/O and code generation.
- `src/mne_nodes/resources/`: packaged icons, images and welcome-tour examples.
- `tests/`: tests, shared fixtures and the tiny BIDS dataset; not installed.
- `development/`: development-only helpers; not installed. Run helpers from the
  repository root, for example `python -m development.param_tester`.

The project uses a `src` layout: install it before importing or testing it.
Use `python -m pytest` (or `conda run -n mnedev python -m pytest`) from the
repository root. Pytest discovers only `tests/` and uses importlib import mode;
it does not add `src/` to the import path. Configuration lives in `pyproject.toml`.
CI tests a non-editable installation to catch missing modules and resources.

The module path has changed from `mne_nodes.pipeline` to `mne_nodes.backend`.
Update external plugins and scripts that import this module. The
`mne_nodes.gui` module path, package name and `mne_nodes` launch command
remain unchanged.

## Docker

See the [Docker GUI development guide](docs/source/development/docker_gui.rst)
for the cross-platform container launcher and X server requirements.

## Workflow for contributing
1. Create a branch for changes: `git checkout -b <branch-name>`
2. Commit changes: `git commit -am "<your commit message>"`
3. Push changes to your forked repository on GitHub: `git push`
4. Make a new _pull request_ from your new feature branch
5. After review, your changes can be merged into the main-branch
