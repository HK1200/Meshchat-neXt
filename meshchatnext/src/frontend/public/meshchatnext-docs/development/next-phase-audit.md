# Next-phase capability audit — 2026-10-28

Development status; no release or Windows parity claim.

## Peer Radio2

Primary firmware reference: https://mikecarper.github.io/MeshCore/radio_profiles/#discover-the-local-radio2-profile

Cascade supports requesting a version-1 Radio2 trailer on public zero-hop discovery (request flag 0x02). A valid profile reports frequency, bandwidth, SF, CR, RX/RXTX and temporary status. The two-byte [1,0] result combines off, unsupported and foreign-protocol states: show “unavailable”, never assert “disabled”. Missing/malformed/future trailers stay unknown. Discovery is unauthenticated, so label results reported, with reception time and source; do not present cryptographic confirmation.

The installed meshcore library exposes raw CONTROL_DATA before its DISCOVER_RESPONSE parser, but the latter discards the trailer. Its send_node_discover_req helper cannot set the new request bit. Integration must use the existing low-level send_control_data API and raw-event subscription, correlate a fresh request tag, demand full public keys and zero hops, preserve session/owner boundaries, respect discovery throttling, and cache the observation separately from node “last heard” metadata. No network requests during normal UI polling. Nearby repeaters only; absence of this extension says nothing reliable about remote clients’ media support.

Implemented locally: strict decoder, raw-event discovery integration with matching tag/full-key/zero-hop checks, owner-scoped persistent observations, and node/map/visualiser report details. Existing explicit nearby discovery requests the extension; normal polling sends no probes. Tests cover malformed/legacy/future replies, owner changes, persistence and unchanged heard times. A live nearby discovery returned a legacy reply without a Radio2 trailer; its status remained unknown. Positive detection with a compatible Cascade repeater is still unverified because none is available. Local review preview at http://127.0.0.1:5183/ uses simulated replies and real UI components.

## Windows 11

Existing infrastructure: package.json has x64/arm64 portable and NSIS targets, dist:win-x64/dist:win-arm64 scripts; scripts/ci/github-build-windows.sh verifies backend manifest and frozen runtime; build-release.yml has a Windows runner. These are packaging infrastructure, not tested service parity.

Verified blockers from local source:

- meshcore_transport.transport_platform returns unsupported on Windows. Desktop USB validation requires /dev character devices, and BLE targets require Linux-style MAC addresses. Implement Windows COM-port enumeration/validation and WinRT BLE identifiers without removing Linux path protections. Verify independent multi-radio reconnect on actual Windows.
- NodePasswords selects only Linux Secret Service or Android secure storage. Add a Windows credential provider with owner/peer/role isolation; no plaintext fallback.
- sip_desktop_http rejects non-Linux platforms; service status labels Linux and audio echo cancellation uses pactl/PulseAudio. A native Windows SIP helper/audio backend and packaged microphone/speaker testing are required.
- electron/updateApply.js applies AppImage payloads only. Windows needs a separately verified installer handoff, executable signing/trust, cancellation/retry, and data-preserving upgrade tests.
- NSIS artifactName omits architecture while targets include x64 and arm64. Give installers architecture-specific names before producing both variants to prevent collisions.

Next validation order: native Windows build/runtime and dependency audit; transport/credential support; SIP/audio; notifications and offline-map import; backup/restore and signed update upgrade/cancel tests. Actual Windows 11 access is needed before release claims. No Windows package was built, pushed or uploaded during this audit.
