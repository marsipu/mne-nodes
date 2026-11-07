Documentation screenshots
=========================

The ``Render Documentation`` workflow captures the application on
``ubuntu-latest`` before building Sphinx. The runner uploads a
``docs-screenshots-linux`` artifact, which the documentation job embeds in the
:doc:`demo page </documentation/screenshot_demo>`.

On a pull request, download and extract the ``html-docs`` artifact from the
workflow run, then open ``index.html`` to preview the site. No Pages deployment
is made from pull requests. Pushes to ``main`` also publish the site.
The workflow can also be started manually from the Actions tab; only runs on
``main`` deploy to Pages.

GitHub Pages deployment
-----------------------

The workflow uploads the built site as a ``github-pages`` artifact and deploys
it directly using GitHub Actions. It does not commit generated HTML to a branch.
The separate deployment job uses the ``github-pages`` environment and serializes
deployments without interrupting an in-progress deployment.

To migrate an existing branch-based Pages site, open the repository's
**Settings > Pages** and set **Build and deployment > Source** to
**GitHub Actions**. Merge the updated workflow into ``main`` and confirm that
the deployment succeeds and the site loads. The old ``gh-pages`` branch can
then be deleted; the workflow no longer creates or updates it.

Generating images locally
-------------------------

Install the package, PySide6, and the test and documentation extras in your
development environment. For example, on Linux:

.. code-block:: bash

   python -m pip install PySide6 -e ".[test,docs]"
   MNENODES_SCREENSHOT_DIR=docs/source/_static/screenshots/linux \
       python -m pytest tests/test_documentation_screenshots.py

The test can also capture on other systems by setting
``MNENODES_SCREENSHOT_DIR`` to another platform directory. In PowerShell, set
``$env:MNENODES_SCREENSHOT_DIR`` before invoking pytest. Linux needs a display;
on a headless machine use ``xvfb-run -a`` before ``python -m pytest``. The CI
uses the same headless-display setup as the regular GUI tests.

For a complete local site, download the ``docs-screenshots-linux`` artifact
from the same workflow run and extract its ``linux`` directory into
``docs/source/_static/screenshots/``, then run:

.. code-block:: bash

   python -m sphinx -b html docs/source docs/build/html

A local capture updates only the current platform. Sphinx reports missing
images if the Linux artifact has not been downloaded.
Generated PNGs are ignored by Git, not committed or compared pixel-for-pixel.
Without ``MNENODES_SCREENSHOT_DIR``, the screenshot tests are skipped.

Adding a scenario
-----------------

Add a scenario to ``tests/test_documentation_screenshots.py`` and a figure to
the demo page.

The fixture isolates settings and pipeline files in pytest temporary
directories and loads only the packaged example plugin and tiny BIDS fixture.
No sample-data downloads, external plugins, or user recordings are needed.
Assert the expected application state and wait for widgets to be exposed
before capturing; do not rely on fixed sleeps. The capture checks PNG saving
and reloading and normalizes HiDPI images to the widget's logical size.
Qt widget captures include application content, not desktop window frames or
the cursor. The pipeline is fixed at 1000 by 600 logical pixels and the picker
at 900 by 550. Tests assert these exact output dimensions.

These scenarios check that the documented state can be constructed, not
that every pixel matches a baseline. A failed scenario or missing screenshot
artifact blocks the documentation build instead of publishing stale images.
