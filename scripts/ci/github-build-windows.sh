#!/usr/bin/env bash
# Build Windows portable + NSIS installers (electron-builder).
#
# When MESHCHATNEXT_FRONTEND_PREBUILT=1 the script reuses the prebuilt
# meshchatnext/public/ artifact downloaded from the reusable Frontend build
# workflow and only rebuilds the cx_Freeze backend. Otherwise it falls back to
# the full pnpm dist:windows pipeline (frontend + docs + backend).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

git config --global core.longpaths true 2>/dev/null || true

if [[ "${MESHCHATNEXT_FRONTEND_PREBUILT:-0}" == "1" ]]; then
    if [[ ! -f "meshchatnext/public/index.html" ]]; then
        echo "MESHCHATNEXT_FRONTEND_PREBUILT=1 but meshchatnext/public/index.html is missing." >&2
        echo "Download the frontend artifact into meshchatnext/public/ before invoking this script." >&2
        exit 1
    fi
    pnpm run dist:windows-prebuilt
else
    pnpm run dist:windows
fi

# Windows SIP must not silently disappear when its native build was omitted.
if [[ ! -f build/exe/bin/meshchatnext-sip.exe ]]; then
    echo "Native Windows SIP helper is missing from the frozen backend." >&2
    exit 1
fi

# Catch extraResources dropping manifest-hashed files before the unpacked
# staging tree is pruned. A missing file surfaces at runtime as an integrity
# warning that blocks onboarding.
for unpacked in dist/win-unpacked dist/win-*-unpacked; do
    if [[ -d "$unpacked" ]]; then
        node scripts/ci/github-verify-backend-manifest.mjs "$unpacked"
    fi
done

bash scripts/ci/github-prune-electron-dist-staging.sh
bash scripts/ci/github-verify-electron-dist.sh win

# Ensure AppContainer/Landlock/Seccomp modules shipped in the frozen backend.
if [[ -d build/exe ]]; then
    bash scripts/ci/github-verify-frozen-sandbox.sh build/exe
    bash scripts/ci/github-verify-frozen-runtime.sh build/exe
    bash scripts/ci/github-verify-frozen-codec2.sh build/exe
    bash scripts/ci/github-verify-frozen-umsgpack.sh build/exe
    bash scripts/ci/github-verify-frozen-bleak.sh build/exe
fi

# Optional packaged smoke (manual / future CI job on a Windows runner):
#   MESHCHAT_APPCONTAINER=1  start the portable exe and assert
#   GET /api/v1/server/security reports appcontainer_active true.
# Disable with MESHCHAT_APPCONTAINER=0 if LPAC DLL load fails on a given host.
