# Updates

Meshchat neXt supports signed, channel-based updates delivered through the
configured release endpoint. The HK1200 distribution uses GitHub Releases. Every update decision is anchored on a signed manifest, not
on HTTPS alone: the manifest carries a Reticulum identity signature, and
the app verifies it against the pinned release signer before trusting
anything inside.

## HK1200 release feeds

Stable Android builds with platform feed support check the [android-stable signed feed](https://github.com/HK1200/Meshchat-neXt/releases/download/android-stable/latest.rsm) and the [shared signed feed](https://github.com/HK1200/Meshchat-neXt/releases/latest/download/latest.rsm). They offer the newest verified APK compatible with the device. Windows uses the shared feed and Linux uses [linux-stable](https://github.com/HK1200/Meshchat-neXt/releases/download/linux-stable/latest.rsm). Older Android builds only know the shared feed and need one upgrade to gain platform feed support.

To publish an Android hotfix, publish the signed APKs to a versioned Android release. Put its signed `latest.rsm` on the `android-stable` release. The manifest's tag must name the versioned release that hosts the APKs. Check the manifest signature and verify every APK's hash and size before replacing the pointer.

The Windows 0.1.5 executables are unsigned for Authenticode. Their signed-feed entries authenticate package size and SHA-256; source integrity signatures and update-feed signatures do not substitute for Windows executable signing. Back up your profile before installing an update and keep OS protections enabled.

## Channels

Updates follow the channel baked into your build:

- `stable` builds track `release/` on the CDN.
- `beta` builds track `beta/`.
- `testing` builds track `testing/`.
- `local` (self-built) installs never auto-check; the section shows as
  disabled.

## Automatic check

In Settings, under the Maintenance tab, open **Updates** and press
**Check for updates**. The app fetches
`<cdn>/<track>/latest.rsm`, verifies the signature and signer hash,
compares versions, and lists the artifacts that match your platform and
architecture. Anything that fails verification is rejected before it is
ever downloaded.

## Download and apply

Press **Download and stage**. The app downloads the matching artifact to a
temporary file, re-verifies its size and SHA-256 against the signed
manifest, then moves it to a pending folder. For AppImage builds you get
a **Restart to apply** button: the desktop shell re-hashes the staged
file once more, swaps it over the running image (keeping the previous
image as a `.bak` rollback copy), and relaunches.

For packages the app cannot apply itself (deb, rpm, flatpak, wheel, pyz,
APK), the staged file is verified and left ready with install
instructions. Use **Show file** to open its folder.

## Ubuntu 26.04 desktop launch

For a normal desktop launch on stock Ubuntu 26.04, install the verified
`.deb` for your architecture and open **Meshchat neXt** from the app menu.
On x86-64, for example:

```sh
sudo apt install ./MeshchatNext-v0.1.14-linux-amd64.deb
```

Ubuntu's default AppArmor policy restricts the unprivileged namespaces
Chromium needs to sandbox the portable AppImage. A double-click can start
the AppImage and then stop before the window opens. The Debian package's
installed desktop entry works with Chromium sandboxing enabled. Use the
package manager to apply subsequent Debian package updates.

If you specifically need the AppImage contents on an Ubuntu system you
administer, extract the verified AppImage as your regular user. Install the
extracted directory as root at a fixed path such as
`/opt/meshchat-next-appimage` and allow `userns` in an AppArmor profile
attached to exactly `/opt/meshchat-next-appimage/meshchat-next`. Launch the
installed `AppRun` from a desktop entry. Keep the directory root-owned and
protected from writes by ordinary users. Use an exact attachment path for
the installed executable. [Ubuntu AppArmor profile example](https://documentation.ubuntu.com/release-notes/24.04/#unprivileged-user-namespace-restrictions)

## Manual update files

If you downloaded an update file yourself (from GitHub Releases or the
CDN), use **Apply update file** in the same section. The app hashes the
file and accepts it only if its SHA-256, size, platform and architecture
exactly match an entry in the _currently published signed manifest_.
This means:

- The app must be able to reach the CDN once to fetch the signed
  manifest. Verification is cryptographic; the network answer cannot be
  forged without the release private key.
- A stale file for an older release is rejected once a newer manifest is
  live.
- A file that is not listed in the manifest is rejected even if it came
  from a trusted-looking source.

## Security model

- The manifest signature is the trust anchor. A hostile CDN or MITM can
  withhold or delay updates, but cannot forge or alter a manifest.
- Artifact integrity is enforced twice: at download time against the
  signed manifest, and again at apply time before any file is replaced.
- `minimum_version` in the manifest is enforced as an anti-rollback
  floor.
- Artifact paths in the manifest must be relative paths inside the tag
  directory; traversal and absolute paths are rejected.
- Environment overrides for debugging:
  `MESHCHATNEXT_UPDATE_BASE_URL` (CDN base), `MESHCHATNEXT_UPDATE_SIGNER`
  (hex signer hash), `MESHCHATNEXT_UPDATE_DISABLED=1`.
