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

Console output uses Rich for logging and progress, and ansi2html for GUI
rendering. ANSI conversion runs in the stream worker; the GUI receives bounded
batches rather than an update for every write.

To try the error dialog and its reporting flow, run
`conda run -n mnedev python -m development.error_dialog_tester` (or
`python -m development.error_dialog_tester` in your development environment).
The helper raises an intentional error without reading any data. Try copying
the traceback, optionally including real system diagnostics, and opening the
editable, redacted report preview with **Open GitHub issue…**. No pipeline is
loaded, so plugin and dataset summaries are unavailable. Diagnostics are collected
in a worker dialog so the interface stays responsive while system info is gathered.
**Copy report and open GitHub** opens a real issue draft in your browser; it does
not submit an issue.
Cancel the preview to avoid opening the browser, and do not submit demo reports.

Tests default to `mne_nodes.gui_mode = False`, including during collection and
controller setup, so backend tests do not open JSON/plugin-loading progress
dialogs. This does not prevent `pytest-qt` tests from constructing and exercising
widgets directly. Tests needing application-level GUI routing (dialogs,
notifications or welcome-tour initialization) can request the `gui_mode` fixture
or use `@pytest.mark.gui_mode`. The marker enables GUI mode before any fixture
setup and also works on classes or modules; the fixture enables it when that
fixture runs. Mode changes are restored after each test. Prefer opting in only
for tests that need these GUI code paths, and mock unrelated prompts as usual.

The module path has changed from `mne_nodes.pipeline` to `mne_nodes.backend`.
Update external plugins and scripts that import this module. The
`mne_nodes.gui` module path, package name and `mne_nodes` launch command
remain unchanged.

## Docker

See the [Docker GUI development guide](docs/source/development/docker_gui.rst)
for the cross-platform container launcher and X server requirements.

## Publishing releases

Package versions are derived from Git tags by `hatch-vcs`; do not manually
set a version in `pyproject.toml`. To publish through GitHub's Releases page:

1. Merge the release changes into `main`, wait for CI to pass, and smoke-test
   the GUI. Review the readiness notice in the README before entering beta;
   retain the warning about production analysis until it is appropriate to
   remove it.
2. Create a release with a new tag targeting the intended commit on `main`.
   Use Python version notation, for example `v0.1.0b1` for the first beta,
   `v0.1.0rc1` for a release candidate, or `v0.1.0` for the final release.
3. Generate and review release notes, including known limitations and
   installation instructions. Check **Set as a pre-release** for alpha, beta
   and release-candidate versions; leave it unchecked for final releases.
4. Publish the release. The **Upload to PyPi** workflow reruns the shared test
   suite, checks that the tagged commit belongs to `main`, and verifies that
   both built distributions match the tag and the pre-release flag before
   uploading to PyPI. Publishing cannot be triggered manually.
5. Confirm the workflow succeeded and the version appears on PyPI. Install
   that exact published version in a clean environment, for example
   `pip install mne-nodes==0.1.0b1`, and smoke-test the GUI before announcing it.

Users can opt into pre-releases with `pip install --upgrade --pre mne-nodes`.
PyPI versions cannot be overwritten: publish a new version (for example
`v0.1.0b2`) for fixes instead of moving or reusing an existing release tag.
If validation fails before upload, fix the issue and rerun the failed workflow;
do not use a manual untagged publish as a workaround.

## Workflow for contributing
1. Create a branch for changes: `git checkout -b <branch-name>`
2. Commit changes: `git commit -am "<your commit message>"`
3. Push changes to your forked repository on GitHub: `git push`
4. Make a new _pull request_ from your new feature branch
5. After review, your changes can be merged into the main-branch
