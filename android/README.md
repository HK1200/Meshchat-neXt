# Meshchat neXt Android (Chaquopy)

Native APK with embedded Python (meshchatnext/) and a WebView UI.

## Prerequisites

- Android SDK (ANDROID_HOME / ANDROID_SDK_ROOT) with cmdline-tools and a matching **NDK** (see android/app/build.gradle for the pinned NDK version used in CI).
- **JDK 17** (Temurin or compatible).
- Chaquopy vendor wheels under android/vendor/ (build locally with bash scripts/build-android-wheels-local.sh from repo root, or use CI artifacts). That script builds native recipes under android/chaquopy-recipes/ and also vendors pure-Python wheels such as bleak and httpx[http2] (for bundled RNS-over-HTTP / HTTPInterface).

## Lint and static analysis

- **Android Lint** (Java, Kotlin, manifests, resources): from android/, run ./gradlew --no-daemon :app:lintDebug. HTML report: app/build/reports/lint-results-debug.html. CI runs this in the Android workflow when tests run.
- **SAST (GitHub CodeQL)**: the repository workflow includes a java-kotlin matrix entry (see .github/workflows/security.yml) for GitHub's security analysis on default branches and PRs.

## Launcher shortcuts, language

- **App shortcuts** (long-press the launcher icon): open **Messages** (meshchatnext://app/messages) and **Call** (meshchatnext://app/call). The WebView handles these in App.vue via handleProtocolLink.
- **Per-app language (Android 13+)**: android:localeConfig points to res/xml/locales_config.xml. Add translated values-xx/strings.xml for Android notification/shortcut strings. The in-app language still comes from Meshchat neXt server config.

## Build

From repo root:

```bash
bash scripts/build-android-wheels-local.sh
cd android
./gradlew --no-daemon :app:assembleDebug :app:assembleRelease
```

There is a **single** application variant (no product flavors). Gradle syncs the **entire** meshchatnext/ tree into app/src/main/python/meshchatnext/ (including public/repository-server-bundled for the in-app repository server), and syncs vendored **vendor/lxmfy/lxmfy** into app/src/main/python/lxmfy/ (required for bots. Not installed via Chaquopy pip) plus **vendor/rns_filesync/rns_filesync** into app/src/main/python/rns_filesync/ (required for FileSync). The fetchRepositoryBundledWheels task runs before sync when bundled wheels are missing. If repo root dist/meshchat_next-*.whl exists (e.g. from python -m build --wheel -o dist .), that wheel is preferred over PyPI for the bundled set.

### Native ABIs (universal APK)

Release and debug artifacts are **universal APKs** only: one APK per build type, embedding the native libraries for each ABI selected at build time.

- **-PmeshchatnextAbis=...** or **MESHCHATNEXT_ABIS**: comma-separated list from arm64-v8a, x86_64, armeabi-v7a (default: all three). This controls which .so variants are merged into the single universal APK, not separate per-ABI store listings.

### Outputs

Each build produces:

- Debug: app/build/outputs/apk/debug/app-debug.apk
- Release (unsigned until you sign): app/build/outputs/apk/release/MeshchatNext-v*-android-universal-unsigned.apk
- GitHub release asset (after signing): `MeshchatNext-v<version>-android-universal.apk`

### Signing release APKs

See repo root scripts/sign-android-apks.sh (default glob targets outputs/apk/release/).

## Troubleshooting

1. Confirm android/vendor/ contains required .whl files from the wheel build script.
2. Codec2 (voice messages, LXST Codec2 profiles): wheels must include pycodec2/libcodec2.so beside pycodec2.so. The wheel build script repacks automatically. For an existing android/vendor/ tree run python3 scripts/repack-android-pycodec2-wheels.py. Gradle also runs this before sync and copies `libcodec2.so` into jniLibs per ABI.
3. Run ./gradlew :app:assembleDebug with --stacktrace if Python sync or Chaquopy pip steps fail.
4. Re-run ./gradlew :app:assembleDebug after changing meshchatnext/ assets. Sync runs on merge Python sources tasks.

See [../LICENSE](../LICENSE) for full text and notices.

### Repairing a Codec2 extension without its Python initializer

The Android pycodec2/pycodec2.so must export PyInit_pycodec2. Bundling libcodec2.so alone does not make an extension importable. Use scripts/android/rebuild-pycodec2-wheel.py with the pycodec2 4.1.1 input wheel, the matching NumPy 1.26.2 wheel, the Chaquopy Python 3.11 target ZIP for that ABI, and the Android NDK 27.3.13750724 LLVM toolchain directory. Pass a new wheel filename under a separate output directory to --output, preserving the original wheel.

The script verifies the pinned generated C source and downloads checksum-pinned Codec2 headers. It compiles the extension for Android API 24 with 16 KiB alignment, verifies the exported initializer, updates the wheel RECORD, and writes input/output provenance. Repeat with --abi arm64-v8a, --abi x86_64, and --abi armeabi-v7a using their respective inputs. Copy the repaired wheels into the private vendor directory before building. Test actual encode and decode on Android before publishing.
