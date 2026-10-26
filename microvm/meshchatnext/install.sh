#!/bin/sh
# Install Meshchat neXt inside the Alpine guest.

set -eu

mkdir -p /data/meshchatnext/config /data/meshchatnext/storage /opt/service

# Install from PyPI — use a venv to keep the system python clean
python3 -m venv /opt/service/meshchatnext-venv
/opt/service/meshchatnext-venv/bin/pip install --quiet meshchat-next

ln -sfn /opt/service/meshchatnext-venv/bin/meshchatnext /usr/local/bin/meshchatnext
echo "meshchatnext installed: $(/opt/service/meshchatnext-venv/bin/meshchatnext --version 2>&1 || echo 'ok')"
