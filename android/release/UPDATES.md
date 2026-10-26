# neXt Android updates

This preview has no configured update publisher. Both `MESHCHATNEXT_UPDATE_BASE_URL` and `MESHCHATNEXT_UPDATE_SIGNER` must be set deliberately before update discovery is enabled. No inherited application signing identity is trusted by default.

The custom feed uses `BASE/TRACK/latest.rsm` and `BASE/TRACK/TAG/FILE`. Configure a separate neXt update identity and Android release certificate, store private keys outside the source tree, and verify the final manifest and APK before publication. The `next-release-check.yml` workflow requires explicit expected signer and certificate values.

Android serves a staged APK through `/api/v1/update/payload`, rechecking its checksum before download. Android verifies the package signing certificate when the owner installs it. Updates are not installed silently.

# Voicemail speech

Android generates greetings using an installed offline Android speech voice. `VoicemailTextToSpeech` runs initialization on the Android main thread and waits on a Python worker, with bounded waits and cleanup on every path. Speech text is never intentionally sent to a network voice. Voice/language uses an Android voice name or BCP 47 language code, such as `en-US`. Existing speed and pitch controls are mapped to Android rates; eSpeak word-gap controls remain desktop-only.

The status API exposes `has_tts` and `tts_provider`, retaining `has_espeak` for older clients. Recording and uploading greetings remain available without a speech engine. Failed generation or encoding preserves the existing greeting.

Android voicemail encoding also requires packaged libogg. Provision it with `python3 scripts/android/provision-ogg.py --abis arm64-v8a,x86_64,armeabi-v7a`. The source archive is pinned to the official Xiph SHA-256, and Gradle fails packaging when a selected ABI is missing the library. The Android PyOgg discovery hook loads it from the native library directory alongside libopus.

Greeting playback also requires libopusfile. After provisioning Opus and Ogg, run `python3 scripts/android/provision-opusfile.py --abis arm64-v8a,x86_64`. Its release source and dependency headers are checksum-pinned; only the local-file decoder is built, without the HTTP/URL backend. Gradle verifies the library for each selected ABI before packaging.
