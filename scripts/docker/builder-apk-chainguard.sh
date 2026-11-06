#!/bin/sh
# SPDX-License-Identifier: 0BSD
# Chainguard/Wolfi builder-stage compile toolchain.
set -eu

apk add --no-cache build-base git pkgconf openssl-dev libffi-dev linux-headers

# Keep the builder XML parser on the same fixed ABI-compatible library.
apk add --no-cache --upgrade 'libexpat1>=2.10.0-r0'
