#!/usr/bin/env bash
# SPDX-License-Identifier: 0BSD
# Exercise the packaged launch path without changing system sandbox policy.
set -euo pipefail
target="$(realpath "${1:?AppImage or installed desktop entry required}")"
profile="$(mktemp -d)"
trap 'tail -30 "$profile/launch.log" 2>/dev/null || true; rm -rf "$profile"' EXIT
export MESHCHAT_STORAGE_DIR="$profile/data"
export MESHCHAT_RETICULUM_CONFIG_DIR="$profile/rns"
export XDG_CONFIG_HOME="$profile/config"
mkdir -p "$MESHCHAT_STORAGE_DIR" "$MESHCHAT_RETICULUM_CONFIG_DIR" "$profile/launch"
printf '[reticulum]\n  enable_transport = No\n  share_instance = No\n  discover_interfaces = No\n  autoconnect_discovered_interfaces = 0\n[interfaces]\n' > "$MESHCHAT_RETICULUM_CONFIG_DIR/config"

if [[ "$target" == *.AppImage ]]; then
    install -m 0755 "$target" "$profile/launch/${target##*/}"
fi

timeout 150 dbus-run-session -- xvfb-run -a bash -s -- "$target" "$profile" <<'DISPLAY'
set -euo pipefail
target="$1"
profile="$2"
if [[ "$target" == *.AppImage ]]; then
    export NO_AT_BRIDGE=0
    thunar "$profile/launch" > "$profile/launch.log" 2>&1 &
    /usr/bin/python3 - "${target##*/}" <<'PY'
import subprocess
import sys
import time

import pyatspi

name = sys.argv[1]

def find(node):
    if node is None:
        return None
    if node.name == name:
        rect = node.queryComponent().getExtents(pyatspi.DESKTOP_COORDS)
        if rect.width > 0 and rect.height > 0:
            return rect
    for child in node:
        found = find(child)
        if found is not None:
            return found
    return None

for _ in range(40):
    rect = find(pyatspi.Registry.getDesktop(0))
    if rect is not None:
        subprocess.run(
            ["xdotool", "mousemove", str(rect.x + rect.width // 2),
             str(rect.y + rect.height // 2), "click", "--repeat", "2", "--delay", "100", "1"],
            check=True,
        )
        print("Double-clicked the AppImage in Thunar.")
        break
    time.sleep(0.5)
else:
    raise SystemExit("The AppImage icon was not visible in Thunar.")
PY
else
    gio launch "$target" > "$profile/launch.log" 2>&1
fi
for attempt in {1..55}; do
    if curl -fkSs --max-time 1 https://127.0.0.1:9338/api/v1/status 2>/dev/null |
        python3 -c 'import json,sys; s=json.load(sys.stdin); sys.exit(not (s.get("network_ready") and s.get("ui_ready")))' 2>/dev/null; then
        for pid in $(pgrep -f 'meshchat-next .*--type=renderer'); do
            if ! tr '\0' '\n' < "/proc/$pid/cmdline" | grep -qx -- '--no-sandbox' &&
                grep -Eq '^Seccomp:[[:space:]]+2$' "/proc/$pid/status"; then
                echo "Desktop launch reached Reticulum readiness with a seccomp-filtered Chromium renderer."
                exit 0
            fi
        done
    fi
    if grep -Eiq 'SUID sandbox helper binary|No usable sandbox' "$profile/launch.log"; then
        if [[ "$target" == *.AppImage ]]; then
            echo "Stock AppImage launch reached Chromium and was blocked by its sandbox startup check."
            exit 0
        fi
        exit 1
    fi
    sleep 2
done
exit 1
DISPLAY
