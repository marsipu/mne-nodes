Docker GUI
==========

The Docker image can display its Qt window through the host X server. This is
useful for interactively testing the Linux container; run the application
natively for ordinary desktop development.

From the repository root, build the image whenever the Dockerfile, Python
dependencies, or application source changes:

.. code-block:: shell

   python docker/build_docker_image.py

Launch the already-built image with:

.. code-block:: shell

   python docker/run_docker_gui.py

Close the MNE-Nodes window to stop the container. Since the container is
removed after it closes, each launch starts with fresh application settings.

Windows
-------

Install `VcXsrv <https://sourceforge.net/projects/vcxsrv/>`_. The launcher
starts it on display ``0`` in multi-window mode when it is not already running.
Windows Firewall may ask to allow VcXsrv; allow it for private networks. To
configure or start VcXsrv manually, use:

.. code-block:: shell

   python docker/run_docker_gui.py --no-start-x-server

VcXsrv is started with ``-ac`` to permit Docker Desktop to connect to the local
X server. Use this only on a trusted local machine.

Linux
-----

Run the launcher from an active X11 session. It temporarily grants the local
root user access to the X server and mounts ``/tmp/.X11-unix`` into the
container; that permission is removed when the container exits. Wayland
sessions require an active XWayland compatibility server.

macOS
-----

Install `XQuartz <https://www.xquartz.org/>`_, then enable **Allow connections
from network clients** in XQuartz Settings > Security and restart XQuartz. The
launcher connects through Docker Desktop at ``host.docker.internal:0`` and
temporarily grants localhost access. This setup is intended for local use only.

Do not set ``START_XVFB=1`` for visible windows: Xvfb is an in-container,
invisible display intended for headless testing.
