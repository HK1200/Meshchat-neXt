# Meshchat neXt Android preview preparation

The independent application ID is `com.haadkoe.meshchatnext`; its local backend uses port 8012. Version metadata comes from `next-release.json`. No official publication or production signing identity is configured.

## Reproducible native inputs

`native-inputs.json` pins 68 wheel/JNI inputs. Run `scripts/android/prepare-stable-build.py --native-inputs INPUT_ROOT --frontend PREPARED_PUBLIC --dest NEW_DIRECTORY` to verify every hash and assemble a fresh build tree from tracked sources. It excludes untracked backups and keys. Rebuild and copy the frontend after changing its source, and retain source provenance with the artifact.

Use JDK 17, Python 3.11, and the pinned Android SDK/NDK:

```sh
./gradlew :app:testDebugUnitTest :app:lintDebug :app:assembleDebug -PmeshchatnextAbis=arm64-v8a
```

MeshCore support is enabled by default. The optional `meshchatnextWithoutMeshCore` property produces a build without the companion SDK. Diagnostic instrumentation is separate from the user app.

## Local validation

The initial preview passed 37 Android unit tests, Android lint, and assembly. Its 152 arm64 native payloads match the previously device-tested integration APK exactly and pass 16 KB LOAD/RELRO checks. The renamed backend starts on the 13. Fresh Android permissions still require owner interaction before live radio testing in this new application ID.

The earlier HK source and its detailed native/NumPy validation history are preserved separately. Those historical results do not imply that every upstream NumPy test passes on Android. Complete suite and UI results for this release are recorded in `docs/next` and the local review output directory.

A production release requires a reviewed source snapshot, a separate permanent signing key, final APK/native/certificate/checksum verification, and explicit publisher configuration. Nothing in local preparation publishes artifacts.
