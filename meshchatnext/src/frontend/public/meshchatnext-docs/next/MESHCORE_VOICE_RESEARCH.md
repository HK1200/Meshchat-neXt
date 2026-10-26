# MeshCore voice investigation

Reviewed 2026-10-25. User requested Telephone integration if Radio2 voice calls are possible.

## Findings

The installed Cascade Radio2 profile routes media packets; it is not an LXST or live-call backend. MeshCore Open TAK documents recorded clips (up to 20 seconds) with VE3 text announcements, on-demand fetch, fragmented transfer and missing-packet requests. Its published feature list does not specify live call negotiation, ringing, duplex audio, or a compatible live-call protocol.

Sources:

- https://github.com/jade-on-mesh/meshcore-open-tak#how-voice-works
- https://github.com/jade-on-mesh/meshcore-open-tak/blob/main/documentation/media-mesh.md
- https://github.com/jade-on-mesh/meshcore-open-tak/blob/main/docs/vox-voice.md
- https://github.com/mikecarper/MeshCore/releases/tag/v1.18.0.1-halo-keymind-cascade-dev-03214a16

## Decision

Do not expose a working-looking live-call toggle or route a MeshCore public key into the Reticulum telephone dialer. Telephone Phonebook and Contacts gain separate Reticulum/MeshCore choices, MeshCore user discovery, search, explicit contact addition, and clearly labelled MeshCore messaging. No name-based linking. Reticulum calling remains unchanged.

## Next implementation boundary

Before enabling MeshCore voice, implement and validate compatible VE3 clip encoding/decoding, bounded fragment reassembly, fetch authorization, missing-fragment retry limits, expiry and identity isolation, with strict Radio2-only media transmission and primary settings preserved. Existing Codec2 support can be evaluated for reuse. Two compatible clients are needed for interoperability tests. A later live-call mode requires a specified signaling and audio transport, airtime/latency measurements and a separate opt-in; Radio2 support alone must never imply call capability.

## Current implementation and validation

Recorded Codec2 1200 voice clips now have Record, Stop, Preview, Discard and Send controls inside MeshCore direct messages. VE3 envelopes use normal encrypted direct messaging; raw 0x56/0x57 audio and 0x72 fetch packets require a verified Radio2-only media profile, crossing disabled and known one-byte direct routes. Audio itself is **unencrypted over radio**, which is disclosed in the composer and message bubble. There is no live call toggle, channel audio or primary-radio fallback.

On-demand reception validates the saved incoming envelope, bounds sessions/packets/length, ignores unsolicited fragments, deduplicates frames, and retries missing frames at most three times with varied requests and salted replies. Only explicitly announced outgoing clips are served to a matching known contact prefix. Raw requests do not authenticate a full identity: this is a compatibility constraint of the unencrypted MediaMesh protocol, not a secure media transport.

Clips are local, owner/contact scoped, excluded from configuration exports, expire after seven days and use a maximum of 100 cached clips per identity. Cached clips can be played disconnected. Unit tests exercise codec encoding/decoding, two independent clients exchanging a clip with a dropped fragment and retry, route restrictions, cache isolation, unannounced-draft rejection and microphone cleanup. Live Radio2 tests now pass between the owned T1000-E and RAK3401 + RAK13302. Both use the user-confirmed Puget Mesh primary profile (910.525 MHz, BW62.5, SF7, CR4/5), while Radio2 uses the separate MediaMesh profile. Twenty-second synthetic clips transfer fully while backgrounded, cached playback works disconnected, and an interrupted 1/20-part download completes after reconnect and explicit retry without a new announcement.

A real microphone recording was previewed, transferred, and heard by the owner. The owner exposed premature playback caused by resetting the audio source on equivalent conversation polling updates; the fixed multi-source watcher preserves the player through polls and the owner confirmed consistent playback. Actual Android playback reached the complete 8.4-second recording with no media error.

Independent-client interoperability also passed with upstream MeshCore Open TAK/VOX 9.5.0-tak using Codec2 1200. VOX → neXt received all ten fragments and decoded 10.08 seconds; neXt → VOX replayed the owner's original recording. The owner confirmed both directions play through with understandable speech. This validates Codec2 DM clips, not Mimi, live calls, multi-hop RF paths, or channel audio.
