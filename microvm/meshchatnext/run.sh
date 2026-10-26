#!/bin/sh
# Start Meshchat neXt headless on port 8000.

set -eu

mkdir -p /data/meshchatnext/config /data/meshchatnext/storage

exec /opt/service/meshchatnext-venv/bin/meshchatnext \
    --host 0.0.0.0 \
    --port 8000 \
    --headless \
    --storage-dir /data/meshchatnext/storage \
    --reticulum-config-dir /data/meshchatnext/config/.reticulum
