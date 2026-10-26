# Meshchat neXt Android builds

The independent application ID is `com.haadkoe.meshchatnext`; its local backend uses port 8012. Version metadata comes from `next-release.json`. Official downloads use the permanent neXt signing certificate and signed update feed. Never put private signing material in this repository.

## Architecture choices

| APK    | Android architecture      | Native layout    |
| ------ | ------------------------- | ---------------- |
| ARM64  | `arm64-v8a`, 64-bit ARM   | 16 KB compatible |
| ARMv7  | `armeabi-v7a`, 32-bit ARM | 4 KB pages       |
| x86_64 | 64-bit Intel/AMD          | 16 KB compatible |

The app minimum is Android 7 / API 24. SIP's AAudio engine requires Android 9 / API 28; older Android versions show this explicitly and retain the other services.

`native-inputs.json` pins the native wheels and JNI libraries. ARMv7 uses official Chaquopy NumPy/OpenBLAS/GNU Fortran packages; the 64-bit variants retain their validated LLVM native inputs. Original runtime license texts are included in `ANDROID_NUMERICS_NOTICES.txt`.

## Building

Use JDK 17, Python 3.11 and NDK 27.3.13750724. Provision Opus/Ogg/Opusfile, Codec2, SIP and AV1 for the selected ABI before Gradle. On a prepared tree:

```sh
./gradlew :app:testReleaseUnitTest :app:lintDebug :app:assembleRelease -PmeshchatnextAbis=armeabi-v7a
```

Select `x86_64` or `arm64-v8a` for the other variants. Build and retain each single-ABI output separately. Multi-ABI debug/review APKs may contain additional Chaquopy archives; they are not the public single-ABI downloads.

Use `scripts/android/prepare-stable-build.py` with the pinned input root and a prepared frontend to assemble a fresh source tree. It excludes untracked backups and keys. Retain each APK's exact source commit, native inventory, certificate and checksum with the release. All architectures in an application update must be built from the same reviewed source commit.

## Validation

Audit every nested native library with `verify-native-apk.py`, then run Android startup and numerical/media checks on the matching ABI. x86_64 needs both 4 KB and 16 KB emulator checks. ARMv7 can be tested as a genuine 32-bit process on a device advertising `armeabi-v7a`; this does not establish compatibility with every older physical handset. Representative numerical checks are separate from the full upstream NumPy suite.

Keep temporary test packages separate from real app identities, accounts, interfaces and radio selections. Remove only disposable test packages afterward. Do not reinstall or reset a user's working app to test another architecture.
