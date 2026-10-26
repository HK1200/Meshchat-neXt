<!-- SPDX-License-Identifier: 0BSD -->

# Flatpak packaging

This directory holds the AppStream metainfo, desktop entry, and icon used for Flatpak builds. The release pipeline builds the `.flatpak` bundle with `electron-builder` using the `flatpak` target in `package.json`.

## Files

- `com.meshchatnext.app.metainfo.xml` — AppStream metadata for app stores and `appstream-compose`.
- `com.meshchatnext.app.desktop` — Desktop entry used by manual `flatpak-builder` workflows.
- `com.meshchatnext.app.png` — 512x512 icon for hicolor icon themes.

## Release build

The CI pipeline in `.github/workflows/build-release.yml` runs:

```bash
bash scripts/ci/github-build-linux-flatpak.sh
```

This uses `package.json` `build.flatpak` settings and produces `dist/*.flatpak`.

## Manual source build

A full `flatpak-builder` source manifest is not tracked here because the release pipeline uses `electron-builder`. To build from source with `flatpak-builder`, create a manifest that runs the `electron-builder` Flatpak target or repacks a `dist/linux-unpacked` tree, then installs the metainfo, desktop, and icon files from this directory.

## Publication

This local preview has no OSTree remote configured. Build from the reviewed local checkout; do not use another product’s remote for this app.
