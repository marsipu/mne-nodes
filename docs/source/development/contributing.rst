Contributor standards
=====================

Set up a checkout
-----------------

Install the checkout in your existing development environment:

.. code-block:: console

   python -m pip install -e ".[test,docs]"
   pre-commit install
   python -m mne_nodes

The project uses a ``src`` layout; install it before running tests or helpers.
Development helpers run as modules from the repository root, for example
``python -m development.param_tester``. Tests and helpers are not in the wheel.

Code conventions
----------------

* Use double-quoted strings, type hints, f-strings, and ``pathlib`` paths.
* Keep lines within 88 characters. Avoid wildcard imports.
* Document public functions and classes. Comment non-obvious behavior, not
  each individual operation.
* Keep processing logic in plugins. Reuse shared widgets, state services,
  datatype aliases, and semantic colors.
* Surface errors through the existing logging/dialog mechanisms. Do not
  swallow broad exceptions unless presenting the captured error to the user.
* Update the relevant short Usage or Developer page when behavior changes.

Validate narrowly
-----------------

Use the existing ``mnedev`` Conda environment when available:

.. code-block:: console

   conda run -n mnedev python -m pytest tests/test_main_window.py

Use ``python -m pytest`` so Windows spawned workers remain importable with
pytest's importlib mode. Run the narrowest relevant tests first; GUI changes
need pytest-qt coverage. The full suite can download large MNE datasets.
Run pre-commit on changed files for formatting and linting.

Tests isolate settings and logs in temporary directories. Subprocesses must
inherit that isolation or explicitly select their own settings directory.
Use ``monkeypatch.setenv`` for test environment overrides.

For documentation, :doc:`screenshots` explains captures and a strict Sphinx
build. For contribution/release procedures, see the repository's
`CONTRIBUTING.md <https://github.com/marsipu/mne-nodes/blob/main/CONTRIBUTING.md>`_.
