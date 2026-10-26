# SPDX-License-Identifier: 0BSD
"""Android's offline speech engine for voicemail; no desktop executable needed."""

from meshchatnext.android_push_bridge import _is_chaquopy_android


def bridge():
    if not _is_chaquopy_android():
        return None
    from com.meshchatnext import VoicemailTextToSpeech

    return VoicemailTextToSpeech


def available():
    native = bridge()
    return native is not None and bool(native.isAvailable())


def synthesize(text, output_path, *, voice, speed, pitch):
    native = bridge()
    if native is None:
        raise RuntimeError("Android speech engine is unavailable")
    native.synthesize(
        str(text), str(output_path), str(voice or ""), int(speed), int(pitch)
    )
