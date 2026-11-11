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

timeout 150 dbus-run-session -- xvfb-run -a -s "-screen 0 1024x768x24" bash -s -- "$target" "$profile" <<'DISPLAY'
set -euo pipefail
target="$1"
profile="$2"
if [[ "$target" == *.AppImage ]]; then
    thunar "$profile/launch" > "$profile/launch.log" 2>&1 &
    window="$(xdotool search --sync --onlyvisible --class Thunar | head -1)"
    xdotool windowmove "$window" 0 0 windowsize "$window" 920 660 windowfocus "$window"
    xdotool key ctrl+1 F9
    sleep 1
    scrot "$PWD/ubuntu-launch-before.png"
    xdotool mousemove --window "$window" 58 132 click --repeat 2 --delay 100 1
    sleep 1
    scrot "$PWD/ubuntu-launch-after.png"
    echo "Double-clicked the AppImage in Thunar."
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
