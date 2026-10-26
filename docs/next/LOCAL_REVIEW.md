# Meshchat neXt — local release review

Meshchat neXt is a new product preparing its first release. Work remains local pending owner review; no hosted GitHub run or publication is implied.

## Review artifacts

The current local Android artifact is `../../outputs/navigation-back-review/MeshchatNext-release-review-arm64.apk`, with its adjacent SHA-256 file. Exact results, limitations and decisions are recorded in `../../outputs/navigation-back-review/RELEASE_REVIEW.md` and `RELEASE_READINESS_RESULTS.json`. Older artifacts are historical and may omit current features.

This is an arm64 development-signed review build. Application ID: `com.haadkoe.meshchatnext`; Android local backend port: 8012; Electron port: 9338. Production signing and update trust remain publication gates.

## Implemented scope

- Reticulum and MeshCore have independent radio lifecycles, clear network labels, shared conversation/contact surfaces, and explicit contact linking.
- MeshCore channels support unread counts, ordering, mute/mentions-only notifications, replies, and local message blocking. Announcements have separate network lists. Repeater/room management remains available.
- Optional Radio2 controls preserve independent primary settings. Codec2 voice and AV1 photos work in ordinary MeshCore DMs/channels and tactical attachments, with explicit preparation, preview, send, download and cached playback. neXt and Open TAK interoperability checks are recorded in the TAK port report.
- MeshCore map/team controls include points, reports, drawings, routes, team alerts, range/geofences, opt-in Android background position sharing, local TAK files and optional verified TLS TAK sessions. Known drawing/media packages, protocol-v1 negotiation, certificate enrollment and HTTPS package transfers have dedicated UI. Nothing automatically bridges to Reticulum or an external TAK server.
- Channel send status reflects radio acceptance and heard repeats. DM acknowledgments remain distinct from heard repeats. Repeat counts are observed packets, not unique repeater counts or proof of delivery.
- The Meshchat neXt name and geometric N replace active product branding, including startup and launcher artwork. Actual upstream/license references and authenticated legacy backup identifiers remain for provenance and compatibility.

## Publication gates and limits

- Owner review and final guide accuracy check. Full frontend: 4,447 passed; desktop: 179; Android unit: 42. Full backend: 5,630 passed plus 68 subtests, with one outdated API fixture corrected and its contract/behavior recheck passing. Exact skips and subsequent focused checks are in the review report. Hosted CI remains unrun because no code has been uploaded.
- Firmware selection/flashing assistant is explicitly deferred.
- Format limits remain: Mimi audio, large AV1 receive modes and arbitrary ATAK datatypes are unsupported. External TAK server deployments and other Android/desktop architectures still need their own environment checks.
- Configure production signing, publisher/update endpoints, and release trust after owner review. Run hosted and other-platform jobs in their target environments.

Decisions made in the owner's absence are recorded in [DEVELOPMENT_DECISIONS.md](DEVELOPMENT_DECISIONS.md).

### SIP / HOIP review

Telephone now has a clearly labelled SIP calling option; its contacts/phonebook entries have SIP addresses and explicit linking to existing contacts. The editable HOIP server preset contains no user identity. New account setup defaults to secure password saving and allows independent Wi-Fi/mobile selection. SIP enablement controls automatic launch/recovery registration. I2P appears only when a usable SIP/media route exists; this build has no such adapter available on the test phones.

The local outgoing call to the owner's Linphone passed two-way speech testing. Native account add/edit/remove and session-only storage checks passed without changing the original registration. No test account credentials were found in the APK. Focused SIP/sidebar UI tests: 10 passed; Android unit tests: 42 passed; license collector tests: 11 passed. Frontend build, Vue types and targeted lint passed. This is not a long-term battery, carrier, headset or universal call-quality certification.
