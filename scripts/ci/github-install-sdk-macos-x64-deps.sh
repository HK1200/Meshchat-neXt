#!/usr/bin/env bash
# Install only the native dependency needed by the locked Intel Mac signer wheel.
# Never change an owner's Mac: this helper is restricted to hosted CI SDK jobs.
set -euo pipefail
if [[ "${GITHUB_ACTIONS:-}" != true || "${RUNNER_ENVIRONMENT:-}" != github-hosted || "$(uname -s)" != Darwin || "$(uname -m)" != x86_64 ]]; then
    echo "SDK signer prerequisites require the genuine hosted Intel Mac runner" >&2
    exit 1
fi
root="$(cd "$(dirname "$0")/../.." && pwd)"
scratch="$root/temp-tests/sdk-macos-verifier-deps"
mkdir -p "$scratch"
if [[ ! -x /opt/local/bin/port ]]; then
    package="$scratch/MacPorts-2.11.5-15-Sequoia.pkg"
    curl -fsSL --http1.1 --retry 4 --retry-delay 4 --max-time 120 \
        https://github.com/macports/macports-base/releases/download/v2.11.5/MacPorts-2.11.5-15-Sequoia.pkg \
        -o "$package"
    echo "9239720455f9ce593e3cda3d73a58fb769976cb415b5189cebbd05764e52d79b  $package" | shasum -a 256 -c -
    pkgutil --check-signature "$package"
    sudo installer -pkg "$package" -target /
    sudo /opt/local/bin/port -N selfupdate
fi
sudo /opt/local/bin/port -N install openssl
if [[ ! -f /opt/local/libexec/openssl3/lib/libssl.3.dylib || ! -f /opt/local/libexec/openssl3/lib/libcrypto.3.dylib ]]; then
    echo "Locked Intel Mac signer dependency is missing" >&2
    exit 1
fi
/opt/local/bin/port installed openssl3
