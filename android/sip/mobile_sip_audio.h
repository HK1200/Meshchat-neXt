/* SPDX-License-Identifier: 0BSD */
#ifndef MOBILE_SIP_AUDIO_H
#define MOBILE_SIP_AUDIO_H
/* The Android audio adapter accepts mono PCM only. Opus keeps its standard
 * two-channel RTP declaration (pch=2) while encoding/decoding mono speech.
 * Baresip's account selector uses local PCM channels, hence /1 below. */
#define MOBILE_SIP_OPUS_CONFIG "opus_stereo no\nopus_sprop_stereo no\n"
#define MOBILE_SIP_AUDIO_CODECS "opus/48000/1,PCMU/8000/1,PCMA/8000/1"
#endif
