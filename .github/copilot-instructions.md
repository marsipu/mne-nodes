# MNE-Nodes Development Instructions

MNE-Nodes is a Qt GUI application for MEG/EEG data-processing pipelines based on
MNE-Python.

## Environment and Validation

- Run tests, application commands, scripts, and other executable validation in
  the existing `mnedev` Conda environment when it is available. For example:
  `conda run -n mnedev pytest mne_nodes/tests/test_controller.py`.
- Do not install dependencies or create a new environment unless required to
  complete the task.
- Run the narrowest relevant test after a change. GUI tests use `pytest-qt` and
  may require a display or headless-display setup.
- The full test suite can download large MNE datasets; allow it to finish.
- Pre-commit handles formatting and linting. Do not run Ruff separately unless
  the task specifically requires it.

## Project Layout

- `mne_nodes/gui/`: Qt GUI components, including node and parameter widgets.
- `mne_nodes/pipeline/`: pipeline execution, I/O, code generation, and control.
- `mne_nodes/tests/`: pytest and pytest-qt tests.
- `docs/source/`: Sphinx documentation.
- `pyproject.toml`: package metadata, dependencies, and tool configuration.

## Code Conventions

- Use double-quoted strings, type hints, f-strings, and `pathlib` for paths.
- Keep lines within 88 characters and avoid wildcard imports.
- Do not use `except Exception` without re-raising, except when displaying a
  captured exception to the user.
- Add docstrings for public functions and classes.
- Preserve existing UI patterns and test GUI behavior with pytest-qt when
  changing widgets.
