#!/bin/sh
# SPDX-License-Identifier: 0BSD
# Chainguard/Wolfi final-stage packages, pip bootstrap, and meshchat user.
set -eu

# Refresh inherited runtime packages as well as newly installed dependencies.
# Pinned base images otherwise retain fixed vulnerabilities until repinned.
apk upgrade --no-cache
# The dev base image can retain explicit package constraints. Replace those
# constraints with fixed-version floors rather than accepting a no-op upgrade.
apk add --no-cache --upgrade \
    'ca-certificates>=20260909-r3' \
    'ca-certificates-bundle>=20260909-r3' \
    'curl>=8.23.0-r0' \
    'libcurl-openssl4>=8.23.0-r0'
apk add --no-cache opus libffi shadow libseccomp

groupadd -g 1000 meshchat
useradd --uid 1000 --gid 1000 --create-home --home-dir /home/meshchat \
	--shell /sbin/nologin meshchat
mkdir -p /config
chown meshchat:meshchat /config
