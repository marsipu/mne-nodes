#!/bin/bash

set -eu

# Optional: start a virtual display for Qt GUI apps.
if [ "${START_XVFB:-0}" = "1" ] || [ "${START_XVFB:-0}" = "true" ]; then
    if ! pgrep -x Xvfb >/dev/null 2>&1; then
        Xvfb :99 -screen 0 1400x900x24 -ac +extension GLX +render -noreset >/tmp/xvfb.log 2>&1 &
        sleep 2
    fi
    export DISPLAY=:99
fi

# This container is meant to run commands directly, e.g. `mne_nodes` or `bash`.
exec "$@"
