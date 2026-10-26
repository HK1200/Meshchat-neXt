# Meshchat neXt development decisions

This is a separate local release, prepared at the owner’s request. Nothing is to be pushed, published, or uploaded to GitHub before owner review.

- Source starts from the HK 1.0.2 checkout plus the ongoing MeshCore integration. The HK checkout is retained separately. No Git remote is configured in this checkout.
- Product spelling: **Meshchat neXt**. A distinct application ID will keep this release separate from the installed HK app.
- Preserve upstream copyright, licenses, and necessary compatibility identifiers; replace active product branding and first-party graphic assets. Record any remaining old-name occurrences and why they remain.
- Keep MeshCore and RNode connection lifecycles independent. Contact linking remains explicit.
- Channel messages show radio acceptance and heard-repeat counts, without delivery-receipt wording. DMs retain acknowledgments and also need heard-repeat counts. Repeats must be matched to actual observed packets; they do not prove delivery or identify unique repeaters.
- Radio2 is optional. MediaMesh defaults: 911.150 MHz, BW250 kHz, SF7, CR4/5, receive/transmit, automatic preamble. Read saved values before offering defaults. Cross-profile forwarding stays off; media requires Radio2.
- T1000-E full companion firmware was flashed locally from verified v1.18.0.1-halo-keymind-cascade-dev-03214a16. Migration changed CR/path-hash defaults; saved primary values were restored and all 284 contacts/26 channel keys verified.
- Android USB two-way messaging passed. A two-minute check passed with the computer disconnected from the OTG hub; the owner suspects its USB-C cable. Automatic USB re-enumeration recovery remains incomplete: manual refresh/select/connect was needed.
- Tests on shared/public channels are forbidden; use #hk-test-7c91 only.
- The original HK app was no longer running when last checked; it was left untouched. Do not claim continuous RNode uptime across that later period.

## Validation scope

Radio2 controls, heard-repeat matching, branding, Android assembly, Linux backend packaging, and local regression/stress checks are covered in the accompanying validation report. GitHub-hosted checks, Windows/macOS builds, and production signing remain separate validation steps. No hosted checks or uploads were triggered.

## Heard-repeat implementation decision

Use exact encrypted packet fingerprints and ignore changing route/path bytes. Keep repeat observations separate from DM acknowledgments. Counts describe observed retransmissions, not unique repeaters or delivery proof. Tracking is bounded to 512 outgoing packets for ten minutes per live connection; historical observations persist, but packets missed while disconnected cannot be reconstructed.

DM packet matching requires the local radio's identity scalar for ECDH. Export it lazily when sending the first DM in a supported connection, validate its public identity, and retain it only in process memory until disconnection. Never include it in status, logs, database rows, backups without explicit encryption, or repeat records. If firmware disallows export, keep messaging functional and leave DM repeat counts unavailable rather than estimating them. Channel matching uses the already-read channel key in transient buffers.

## Release identity and rebrand decisions

- Keep the preserved HK source untouched; apply rebranding only to this separate release tree.
- Package/application ID: `com.haadkoe.meshchatnext`; Android local backend port: 8012, allowing coexistence with HK and its isolated development build.
- Preview version: Python/npm 0.1.0, Android display 0.1.0-preview.1, version code 1. No tag or release has been created.
- No publisher repository, update endpoint, release signing identity, or maintainer contact has been invented. Disable inherited HK update discovery until the new publisher is configured.
- The geometric mark is an editable SVG N with rounded off-white strokes on a near-black rounded square. Matching raster and Android vector icons are generated from the same geometry. Reticulum and other third-party logos are preserved.
- Preserve actual upstream URLs, copyrights, licenses, and required import-format compatibility; inventory remaining old-name references explicitly.

- Live repeat validation: a dedicated-channel message reached the peer and showed one heard repeat; a private DM reached the peer, was acknowledged as delivered, and showed zero heard repeats. No shared/public channel was used.
- Actual upstream URLs remain provenance/third-party dependencies. New publication and support links are left unconfigured rather than inventing a domain or redirecting users to the old product’s tracker.
- Existing encrypted integration identity backups retain their exact authenticated legacy format string for import compatibility; new exports use the new product identifier.

- Removed the inherited signed source inventory: it authenticates the earlier source, not this derivative. neXt needs its own tree signer before strict release verification can pass. Local unsigned previews report that limitation explicitly. Raspberry Pi release discovery and torrent/Flatpak publication also require explicit neXt endpoints.

- Removed the inherited Cosign public key and old issue/support destinations. A neXt publisher must establish its own signing trust. Preserved real upstream URLs only where needed for third-party provenance, directory fetching, or authenticated legacy backup compatibility.
- Security scans found dependency advisories. A broad dependency refresh was rejected by pnpm’s supply-chain policy for a transitive browser package; that protection was retained. Apply targeted security updates and document any remaining advisory limits.
- The initial heap test reloaded entire documents. Its navigation now stays inside the running Vue app to exercise actual view teardown; budgets were not increased.

- CI branch filters now target this checkout’s `main` branch. Publication credentials, repository URLs, and signing identities remain unconfigured.
- Updated advisory-affected dependencies and inherited version overrides, retaining supply-chain trust checks. Python and JavaScript dependency audits now report zero known vulnerabilities. The package manager added a release-age exception for the fixed fast-uri version; its integrity and trust checks remain enabled.
- Browser memory checks use the static Tools page as the neutral view because About polls diagnostics and changes its DOM. Full document reloads, development hot reloads, and pending teardown no longer distort measurements. Existing growth limits remain unchanged.

- Stress testing found that read-only discovery requests kept retrying after leaving MeshCore settings. Scope those requests to the view and abort both pending fetches and retry delays on unmount. Never cancel or automatically replay radio writes.
- Cross-page browsing exposed a shared Go runtime collision between Micron (Go) and the map/visualizer (TinyGo). Each loader now captures the constructor from its own integrity-verified runtime rather than reusing an unrelated global constructor.

- A desktop route crawl found repeated requests to Android-only paired-radio discovery. Backend status now reports this capability, and the UI avoids unsupported discovery calls on desktop. Real Android permission/adapter errors remain visible.
- Rapid Reticulum conversation switching exposed stale scroll completion and layout-generated scroll events being treated as user intent. Scope readiness to the selected peer and ignore scroll events while the new viewport is loading. Cold-browser tests verify long/short switching and preserve intentional reading positions.

- Desktop Electron also uses its own local backend port, 9338, so it cannot attach to the existing HK desktop backend on 9337. Its trusted origins, loading page, permissions, and orphan-process recognition follow the separate port. Android remains on 8012.

- Android permission grants are controlled by the phone. The new app was installed and its backend started, but runtime permission grants from the computer were rejected by Android. Leave first-run permission approval to the owner; retain the existing radio test app for continuity. Do not migrate its private data automatically.
- Workflow linting with ShellCheck enabled also exposed inherited unused loop variables, unsafe wildcard expansion, and repeated output redirects. Correct these without changing release or publication triggers.

- The coverage run exposed two inherited test assumptions: arbitrary Unicode was being treated as a URL scheme (including valid normalized fragments), and an I2P mode unit test bound fixed port 9999. Generate RFC-shaped schemes and mock the unrelated I2P listener; keep the actual sanitizer and mode assertions unchanged.

## TAK completion and battery-test decisions — 2026-10-25

- Independently implement the public TAK wire formats rather than copy ATAK application code. Support bounded known drawing types and preserve raw reviewed package media; reject unsupported geometry instead of silently converting it to a point.
- Keep certificate enrollment, server credentials and client keys session-only. Use verified TLS and host-bound enrollment. Package transfers require explicit user actions; private visibility is the default server metadata setting, not a claim of end-to-end encryption.
- Install the official ATAK CIV SDK APK temporarily on the 9 for synthetic package import. The owner personally accepted its license. Restore the 9's network settings and remove that disposable test installation afterward; preserve Open TAK/VOX.
- Use a private random-key channel for actual GPS checks, record accuracy/age/battery metadata only, and never export actual test GPS records into interoperability fixtures.
- Battery-only testing exposed Android's long-interval GNSS hibernation: the service stayed alive but only the first fix arrived. Sample GNSS every five seconds while independently limiting RF transmissions to the user's 1/2/5-minute choice. Clearly disclose active GPS use in the control. Add elapsed-time expiry checks plus idle-capable cleanup alarm without a new exact-alarm permission; Android can delay alarm delivery, but no fix is sent past the deadline.
- Reject empty/null owner identities for every API operation whose schema requires an owner. Preserve optional-owner legacy behavior where the schema explicitly allows it.
- All code, synthetic fixtures, reports and APKs remain local. Firmware assistant work remains deferred.

## Offline starter map restore — 2026-10-25

The 9 had no installed offline MBTiles; the 13 already had starter_world.mbtiles. Both APKs contained the bundled 626,688-byte starter, so the discrepancy was not Wi-Fi or missing packaged assets. The 9's initial metadata request and explicit restore failed in shutil.copy2/copystat/_copyxattr: Android rejected copying protected packaged-asset attributes to emulated shared app storage. Use shutil.copyfile into the existing atomic temporary sibling instead, retaining atomic replacement and cleanup without carrying package metadata onto user storage.

The regression simulates protected metadata rejection and verifies initial provisioning, restore, all 341 tiles, and temporary-file cleanup. All 10 starter tests passed; Android assembly passed. The corrected build is installed on both phones. Actual API checks confirmed the 9 now auto-provisions the starter, explicit restore returns 200, both inventories contain the starter, and sampled z0/z1/z4 tiles return matching-sized valid 256×256 PNGs. Bundled coverage is a coarse global z0–z4 basemap, not detailed offline street maps. No network tile download was required and no user map was deleted.

## Native SIP calling (local review)

SIP uses pinned BSD-3-Clause baresip/re 4.12.0, Apache-2.0 Mbed TLS 3.6.7 and the existing Opus 1.5.2 runtime. Native AAudio capture uses Android voice-communication routing and available hardware echo/noise effects. Opus and G.711 are offered; codec negotiation and the network still determine actual quality. SIP is Android 9+ in this first integration.

The editable HOIP preset is `premium.hamsoverip.com:5160`, UDP. No extension or password is bundled. Users can add/edit/remove accounts; one selected account registers at a time. Saving passwords defaults on, with AES-GCM encryption backed by Android Keystore, separate from MeshCore node credentials. Session-only credentials never enter preferences, the web store, backups or status responses. SIP contacts are explicitly linked to other network contacts, never inferred.

The SIP service runs in its own process. Only that process binds DNS/signalling/RTP to an allowed network, leaving Reticulum and MeshCore independent. Wi-Fi and mobile data are individual allowed-network choices; new accounts allow both, prefer Wi-Fi and reconnect on allowed-network changes. A handover may end an existing call. I2P is hidden without a compatible SIP-and-media route; installing an I2P router alone does not provide a UDP gateway to HOIP. No clearnet fallback is represented as I2P.

Enabling SIP persists the connection preference. Saved credentials allow automatic registration on app launch and service recovery, with bounded retry after engine loss. Explicit Disconnect disables automatic connection. Session-only accounts require password re-entry after service loss. Android foreground registration status is updated on registration success/failure. Incoming calls remain manual: baresip `call_accept` creates a ringing call, `ANSWERMODE_MANUAL` is forced, remote auto-answer requests are disabled, and only the explicit Answer action starts an incoming call's microphone/audio.

The first live outgoing call from the 9 to the owner's Linphone on the 13 passed the owner's two-way speech check. The initial incoming test exposed a missing SIP-session handoff, now corrected; it also exposed stale foreground notification text, now corrected. Further incoming/network recovery validation is recorded in the local review notes. No firmware or remote repository changes were made for SIP.


### SIP call screen decision — 2026-10-25
At the owner’s request, removed the managed Android PhoneAccount/dialer preview. SIP uses neXt’s own call controls and incoming-call banner, keeping ordinary carrier calls separate. Removed CALL_PHONE and READ_PHONE_NUMBERS permissions; retained the non-runtime MANAGE_OWN_CALLS declaration required by Android’s background VoIP service and the exported ConnectionService. On startup the SIP service unregisters only its own legacy preview accounts. Saved SIP credentials, registration policy and allowed-network choices are preserved. Dedicated-screen build and six SIP frontend tests passed; incoming-call UX requires a fresh live check after this change.


### SIP registration cleanup — 2026-10-25
Owner observed ten unexpired HOIP connections while neXt reported 403. Server connection-limit hypothesis remains unconfirmed. Source inspection corrected the earlier random-contact explanation: upstream defaults to a stable username; ephemeral listening ports can still create distinct Contact URIs. Pin the app’s isolated SIP listener to UDP 5072, explicitly disable random contact usernames, and send ua_unregister before stopping with a bounded 1.5-second event-loop window (within Java’s five-second stop timeout). Successful registration clears prior errors. Crashes, package replacement and NAT changes can still leave older registrations until server expiry; do not remove all server bindings because other clients may share the account.


### App feature visibility and SIP settings — 2026-10-25
Added Settings → App features with independently saved Reticulum, MeshCore and SIP layout switches; all default on for existing installs. Settings remains reachable with all off. Choices hide network navigation, settings children, shared contacts, messaging/announce controls, SIP links, tools and network map overlays without deleting data. These are device-local layout preferences, not a backend shutdown switch; radios/background services retain separate connection controls. First-start workflow is intentionally unchanged. Added Settings → SIP for all account/password/network preferences. Telephone retains SIP status, dialing and active-call controls plus an explicit Reconnect action for the selected account. No live registration changes are needed to review this UI.


### First launch setup — 2026-10-25
The app and /tutorial now use FirstLaunchSetup.vue; the earlier tutorial remains only as a compatibility/reference component with existing regression coverage. Setup builds only the steps for the selected Reticulum, MeshCore and SIP features. Reticulum identity import accepts the existing raw-file/Base32 API and never deletes the previous identity. Drafts save non-secret choices and, if necessary, the public hash of an imported identity awaiting activation; file contents, private keys and passwords are never written to the setup draft. Setup can be reopened under Settings → App features.

Internet TCP is opt-in. Its editable preferred entry is rmap.world:4242, verified against https://rmap.world/services.html . Repeated setup reuses the matching endpoint and never overwrites its IFAC/network credentials. A dedicated receive-announces API removes only bootstrap_only from enabled TCP client / outbound Backbone interfaces, preserving interface modes, radio parameters, private network secrets and I2P boundaries. Setup enables the five ordinary announce storage categories and the default for future TCP connections, then reloads when necessary. Existing interfaces remain configured.

At the owner’s request, new RNode setup defaults to Bluetooth LE and 914.875 MHz, BW125 kHz, SF8, CR4/7, TX17 dBm. These defaults do not rewrite saved interfaces or the separate MeshCore primary/Radio2 profiles. Bluetooth Classic, USB and RNode-over-IP remain available. RNode creation requires an explicit Add action; discovering paired devices does not connect or transmit a test message.

MeshCore onboarding offers the existing client contents or an explicit backup import. It reuses the validated importer and its receipt/identity-replacement checks. Supported multi-device JSON records are selected and restored individually; valid Bluetooth-address metadata helps select the client, without importing Android bond keys or silently connecting. Android pairing must be completed on the device. A backup selected before connection is retained in memory while its preview is invalidated; imports require preview and Apply. Supported sections are preselected during first launch, but replacing a radio identity still requires explicit confirmation. Public-key-only backups cannot restore private identities, and the UI says so. Unsupported archive formats and sections are not claimed compatible.

Radio2 is optional and defaults to keeping the existing setup. Standard MeshCore text needs no Radio2 firmware. Media opt-in verifies actual firmware capability and chooses either the saved Radio2 profile or an explicitly selected US MediaMesh profile; it preserves primary settings, disables crossing and requires Radio2-only media routing. Firmware downloads and setup links point to https://github.com/mikecarper/MeshCore/releases and https://github.com/jade-on-mesh/meshcore-open-tak/blob/main/documentation/media-mesh.md . No flashing assistant was added. The guide explains compatible peers, region matching, unencrypted radio media and recorded clips rather than live calls.

Expanded imports exposed a scrolling bug during owner review. Both page and fullscreen-modal modes now use bounded scrollable content with the navigation footer outside the scroll area; fullscreen panel sizing respects its padded viewport. The owner also exposed a preview-only zero-count stub: sample imports now count and populate only selected contacts/channels in memory. The preview remains explicitly separate from live radios. Its localhost server now runs in a detached session with logs on the media workspace so temporary command cleanup does not close it.

Validation: 189 frontend tests, 51 backend tests, types, changed-source lint and production frontend build passed before final APK assembly. Browser verification exercised the standalone setup page and actual fullscreen modal, including long forms with a visible fixed footer. These checks do not constitute a real-radio restore or an Android touch/keyboard first-run acceptance test. No live user identity, radio configuration or SIP registration was changed for these setup checks.
