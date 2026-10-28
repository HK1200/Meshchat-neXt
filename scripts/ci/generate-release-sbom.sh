#!/usr/bin/env bash
# Build the public dependency inventory from this exact checkout's lockfiles.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
OUTPUT="${1:-reports/sbom.cyclonedx.json}"
mkdir -p "$(dirname "$OUTPUT")"
trivy fs --format cyclonedx --include-dev-deps     --skip-dirs .git,.venv,node_modules,build,dist,temp-tests     --skip-files vendor/lxmfy/poetry.lock,vendor/lxmfy/docs/poetry.lock     --output "$OUTPUT" .
python3 - "$OUTPUT" <<'CHECK'
import json, sys
with open(sys.argv[1], encoding="utf-8") as stream:
    data = json.load(stream)
if data.get("bomFormat") != "CycloneDX" or not data.get("components"):
    raise SystemExit("Release SBOM is not a populated CycloneDX dependency inventory")
print(f"Verified release dependency inventory: {len(data['components'])} components")
CHECK
