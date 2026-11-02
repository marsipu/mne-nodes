Documentation screenshots
=========================

The ``Render Documentation`` workflow captures the application on
``ubuntu-latest``, ``windows-latest``, and ``macos-latest`` before building
Sphinx. Each runner uploads a ``docs-screenshots-<platform>`` artifact.
The documentation job merges those artifacts and embeds the images in the
:doc:`demo page </documentation/screenshot_demo>` using synchronized
``sphinx-design`` tabs.

On a pull request, download and extract the ``html-docs`` artifact from the
workflow run, then open ``index.html`` to preview the site. No Pages deployment
is made from pull requests. Pushes to ``main`` also publish the site.
The workflow can also be started manually from the Actions tab.

Generating images locally
-------------------------

Install the package, PySide6, and the test and documentation extras in your
development environment. For example, on Linux:

.. code-block:: bash

   python -m pip install PySide6 -e ".[test,docs]"
   MNENODES_SCREENSHOT_DIR=docs/source/_static/screenshots/linux \
       python -m pytest tests/test_documentation_screenshots.py

Use ``windows`` or ``macos`` instead of ``linux`` when capturing on those
systems. In PowerShell, set ``$env:MNENODES_SCREENSHOT_DIR`` before invoking
pytest. Linux needs a display; on a headless machine use ``xvfb-run -a`` before
``python -m pytest``. The CI uses the same headless-display setup as the
regular GUI tests.

For a complete local site, download all three screenshot artifacts from the
same workflow run and extract their platform directories into
``docs/source/_static/screenshots/``, then run:

.. code-block:: bash

   python -m sphinx -b html docs/source docs/build/html

A local capture updates only the current platform. Sphinx reports missing
images if the other platforms' artifacts have not been downloaded.
Generated PNGs are ignored by Git, not committed or compared pixel-for-pixel.
Without ``MNENODES_SCREENSHOT_DIR``, the screenshot tests are skipped.

Adding a scenario
-----------------

Add a scenario to ``tests/test_documentation_screenshots.py`` and figures for
each platform to the demo page. Keep OS tab ``:sync:`` values consistent so
switching platforms updates all examples.

The fixture isolates settings and pipeline files in pytest temporary
directories and loads only the packaged example plugin and tiny BIDS fixture.
No sample-data downloads, external plugins, or user recordings are needed.
Assert the expected application state and wait for widgets to be exposed
before capturing; do not rely on fixed sleeps. The capture checks PNG saving
and reloading and normalizes HiDPI images to the widget's logical size.
Qt widget captures include application content, not desktop window frames,
the cursor, or macOS's global menu bar; the demo keeps the menu inside the
main window on every platform.

These scenarios check that the documented state can be constructed, not
that every pixel matches a baseline. A failed scenario or missing screenshot
artifact blocks the documentation build instead of publishing stale images.
