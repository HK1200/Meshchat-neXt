# Android Opus provisioning

From the repository root, run:

```sh
python3 scripts/android/provision-opus.py
python3 scripts/android/provision-opus.py --verify-only
```

Select a subset with `--abis x86_64,armeabi-v7a` or `MESHCHATNEXT_ABIS`.
Gradle's `:app:verifyOpusJniLibs` checks the Gradle-selected ABIs and is required
by `preBuild`. It never downloads or builds libraries. CI provisions before
running Gradle in the build, tag-build, and emulator workflows.

Existing libraries are checked for ELF class, byte order, shared-library type,
and machine architecture, then left untouched. A bad existing library causes
failure: inspect and explicitly move it aside yourself before provisioning.
ELF validation does not establish an existing binary's source version.
The original arm64-v8a library is preserved; its recorded SHA256 is
`c6f6e0816bbd5812ff72b190dd62278d54904f7127207d5ca9ed2bdb00e63cad`.

Missing libraries require Python 3, CMake, a host build tool, and Android NDK
27.3.13750724. SDK discovery uses ANDROID_SDK_ROOT, ANDROID_HOME, then
~/Android/Sdk; `--ndk PATH` selects the pinned NDK explicitly.
Opus 1.5.2 is downloaded from downloads.xiph.org only when needed. An archive
already present at `.local/opus-1.5.2-android/opus-1.5.2.tar.gz` is reused, or
supply `--source-archive PATH` for an offline build. Every build verifies SHA256
`65c1d2f78b9f2fb20082c38cbe47c951ad5839345876e46941612ee87f9a7ce1`
before extracting fresh sources. A checksum mismatch fails without rebuilding.

Builds use API 24, CMake Release, shared libraries, disabled tests/programs and
custom modes. Logs are kept under `.local/opus-1.5.2-android/provision-ABI.log`.
Finished ELF-verified libraries are published atomically without replacing an
existing destination. No APK is installed, signed, or released by this script.

Run the SDK-independent safety tests with:

```sh
python3 -m unittest discover -s tests -p test_android_opus_provision.py
```

## Native page-size compatibility

Future builds enable NDK r27 flexible page sizes and explicitly set linker
maximum and common page sizes to 16384. This enables 16 KB ELF alignment for
newly built Opus libraries. Existing libraries are still never replaced, and
`--verify-only` remains an architecture check, not a 16 KB compliance check.

The preserved libraries currently have 4 KB LOAD alignment. The current release
also includes other 4 KB-aligned native dependencies (notably LXST filters and
NumPy); changing Opus alone cannot establish whole-app 16 KB compatibility.
A migration must validate all native dependencies, including libraries inside
Chaquopy requirement archives, and test on both 4 KB and 16 KB devices before
replacing any known-working binary. The original arm64 library remains protected.
See https://developer.android.com/guide/practices/page-sizes for Android guidance.
