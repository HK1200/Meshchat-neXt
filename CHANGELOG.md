# Meshchat neXt changelog

## 0.1.14 (Android)

- Give Reticulum and MeshCore direct messages a separate Android alert channel, privacy options and a test button.
- Check the Android stable update feed independently of desktop releases.

## 0.1.13 (Android)

- Share one Android background connection card when SIP and mesh are both active. Incoming call controls remain available.

## 0.1.12

- Refresh active call state each second so a missed live hang-up event does not leave the call screen connected for the idle polling interval.
- Add a visible Android speaker routing control to both Reticulum call views.
- Restore the configured microphone speech filters for Android and browser Reticulum calls, including automatic level control. Correct legacy LXST amplitude gain conversion.
- Direct Android volume buttons to call volume during calls.

## 0.1.11

- MeshCore rooms use saved passwords to sign in in the background when the companion connects. Leaving the room screen keeps the session.
- Correct an ahead-of-phone companion clock before submitting a room post. Distinguish a future saved send timestamp from the companion clock, and keep uncertain send attempts from being retried as new posts.
- Include the checksum-pinned Android Codec2 rebuild tool used to repair the low-bandwidth audio module.

## 0.1.10

- Correct Reticulum call playback pitch and timing and match the negotiated microphone framing when the call profile changes.
- Group Android communication notifications while keeping incoming call answer and decline controls accessible.
- Refresh a peer’s advertised name in conversations without changing a locally saved nickname.
- Show the last location update on selected map pins.

## 0.1.9

- Conversations separates MeshCore and Reticulum threads and makes the network clear when starting a chat. Contact pickers can add a discovered contact after you choose the correct identity.
- Long MeshCore texts split into smaller radio messages. neXt waits for confirmation before sending the next part and keeps unsent text in the draft. Private messages start with flood routing unless a direct route was learned recently, and a direct send without an acknowledgment can fall back to flood once.
- Saved MeshCore repeaters try their stored administrator password first. Repeater administration has grouped access controls, a route check without a password, immediate read actions, and a control for repeating. Admin requests use the companion’s round-trip estimate. An unconfirmed command leaves the session open and later replies are labeled unverified when they could be delayed.
- Share private locations with approved contacts once or for a set duration while neXt is in the foreground. Timed sharing continues when you leave the conversation and updates less often while stationary. Open a received location from the chat or the map. Private telemetry stays out of chat history and message notifications.
- Relay Chat opens its hub and room list from the sidebar. Back from a room returns to the list.
- More groups RNS Interfaces, Tools and Settings. The app labels RNS Identities and RNS Phonebook explicitly. Telephone puts Contacts ahead of the RNS Phonebook and separates its MeshCore, Reticulum and SIP/HOIP sections.

## 0.1.8

- Keep MeshCore room and repeater tabs selected during background refreshes.
- Opt in to signing back into an open room once per radio connection using its securely saved member password.
- Start a MeshCore chat from the searchable contact picker in the phone’s Conversations plus menu or desktop sidebar.
- Share a room server’s name and public key from its node page.

## 0.1.7

- Exchange Family-compatible private MeshCore locations with separately approved saved contacts. Share the device location once through an encrypted direct message, with explicit consent per companion and contact, stale/replay protection, prefix-collision rejection and private map labels. Received location frames do not create chat bubbles or notifications.

- Use source-pinned desktop Python runtimes with Expat 2.10.0 security fixes, including the official CPython backport on Windows, and check the actual parser in frozen builds.

- Build Android’s XML parser against Expat 2.10.0 security fixes, preserving the vendor Python kernel and all other target archive files.

- Reply to MeshCore room posts with a short public quote and author hint, counting the complete reply against the existing 160-byte limit. Reply context and drafts are cleared when changing identity or radio.
- Keep room drafts editable after a confirmed pre-send validation or clock failure. Restore the composer when the exact previous submission receives a definite stored outcome, without automatically transmitting it again.

- Initialize frozen desktop worker support before application imports, preventing propagation-stamp workers from failing during RNS startup. Packaged runtime checks now execute a real synthetic LXMF validation task.

- Prevent desktop startup and tests from terminating another running profile. Linux orphan cleanup requires verified same-user, executable and profile ownership; automatic cleanup stays disabled where ownership cannot be proven.

- Simplify MeshCore repeater and room-server pages with task tabs, grouped administrator actions and collapsed identity details. Room messages open first, and drafts survive tab changes.
- Show saved MeshCore contact names for unique room-author prefix matches, retaining the unverified prefix and avoiding ambiguous matches.
- Apply the shared blocked-phrase and regex rules to incoming MeshCore direct messages, channel posts and room posts before history, unread counts or notifications. Room and channel author hints do not grant contact status, and matching posts never automatically ban a room server.
- Preserve repeater terminal, MediaMesh / Radio2, multi-radio routing and existing Reticulum automatic banishment.

## 0.1.6

- Update Android certificate trust bundles and the packaged Python runtime to address the compromised eMudhra certificate authorities.

- Add an administrator repeater terminal and firmware-aware MediaMesh / Radio2 controls, with explicit command confirmation, profile readback and protection against stale responses after changing radios.

- Expand individual MeshCore message-path candidates to inspect their public key, type and reported position, with a map link when coordinates are available. Partial route maps retain gaps for unknown or ambiguous hops.
- Search saved MeshCore node names and public-key prefixes locally, independently of geographic place search, including while offline.
- Store multiple labelled Home, Office, Mobile or Other SIP destinations per contact. Add an extension from Edit contact to the shared Telephone SIP phonebook without losing existing numbers.
- Move SIP and MeshCore link management into the main contact editor. Put Add contact in the header on phones and make long SIP lists scroll with clear counts and search reset controls.
- Renaming a contact updates only records belonging to the same identity, and stops further rename writes when the active identity changes.

## 0.1.5

- Fixed the mobile sidebar staying open when selecting its current destination, including after Back restores the drawer. Different destinations, sidebar reordering and onboarding Back retain their existing behavior.
- Windows 11 x64 portable and installer packages are published as unsigned binaries. Native default and forced AppContainer UI, static assets, cleanup, installer upgrade and profile preservation were verified. Signed update feeds verify package integrity; they do not provide Windows Authenticode signing. Android retains its permanent APK certificate.

## 0.1.4

- Update download and storage failures stay on the Updates page instead of being mistaken for an expired app login. Android update staging avoids unsupported file-metadata copies on shared storage. Failed partial downloads are removed.
- Updated translation HTML sanitization to address GHSA-83rm-6c8r-g728.

- MeshCore maps animate newly received flood packets as glowing comets with fading tails and node pulses. Unknown, ambiguous and unlocated hops break the animation; one compact expandable badge explains gaps without claiming a node location. Effects are scoped to the selected radio and respect reduced-motion settings.

- SIP registration tries other account-allowed connections after failure and retries unavailable connections periodically. A healthy registered connection stays selected.
- Phone sidebar destinations come into view automatically. More → Reorder sidebar provides Save/Cancel controls, and Android Back cancels reordering.
- Fixed Back during first-start setup.
- MeshCore Your channels includes per-channel All messages, Mentions only and Muted notification controls, with unread totals. These controls change alerts, not the messages displayed.
- Nearby discovery can display a repeater’s reported Radio2 profile in node, map and network details. Legacy replies remain Unknown; no response is not proof of absent support. Positive detection with compatible hardware remains unverified.
- Windows source support includes native SIP/audio, USB/Bluetooth transports and protected credential storage. Windows downloads remain withheld pending signing and final package verification.

## 0.1.3

- Compact expandable map credits and consistent Close/Android Back dismissal of MeshCore visualiser details.

- Switch Network visualiser between Reticulum and MeshCore, choose a companion, and inspect known nodes and latest stored outbound routes with explicit unknown/ambiguous hops.

- Tap MeshCore nodes, or long-press map nodes and position dots for read-only details, including Teams context and a choice between overlapping nodes. Desktop right-click also opens details; Back dismisses the popup.

- Connect multiple MeshCore companions, each with its own identity, receiving and automatic reconnect.
- Choose a combined inbox with radio labels or separate radio views, and select the sending radio in direct conversations.
- Manage each radio’s connection, identity, radio profiles and backups together in its own expandable card.
- Improved Bluetooth recovery after delayed channel replies and prevented repeated discovery during normal status refreshes.
- Linux packages include the Bluetooth D-Bus dependencies required by the frozen application.
- Release dependency inventories are included for scheduled security re-scanning.

## 0.1.2

- Verified Android updates open Android’s installer directly, with clear completion and cancellation feedback and a manual file fallback.
- Updates preserve the existing permission for lock-screen incoming calls.
- SIP incoming calls have a dedicated lock-screen Answer/Decline screen and repeating vibration that stops when answered or declined.
- Added outgoing SIP ringback and improved background SIP connection handling.

## 0.1.1

- Additional Android APKs for 32-bit ARM and x86_64, alongside ARM64.
- Improved landscape scrolling, compact message composers and navigation on phone screens.
- Photo and voice editors use scrollable dialogs so attachment controls cannot push Send off-screen.
- A visible Offline maps control and a verified, one-step regional map download with progress and cancellation.
- Fixed the changelog overlapping setup and the map search field overlapping controls on short screens.
- HOIP live phonebook access from SIP contacts, with clear internet and I2P browser requirements.
- Clear SIP availability on Android versions older than Android 9.

## 0.1.0 — Initial release

### Communications

- Reticulum LXMF messaging and LXST calls, with supported radio, LAN and internet interfaces.
- Independent MeshCore Bluetooth/USB companion connections alongside Reticulum/RNode.
- Clearly labelled conversations, shared contact management and explicit cross-network linking.
- Separate Reticulum and MeshCore announce lists, plus local/flood MeshCore adverts.
- MeshCore channels with unread navigation, ordering, hide/show, deletion, replies, notification modes and local message blocking.
- SIP extension calling with configurable accounts, an editable HOIP server preset, optional secure password storage and automatic reconnection.

### MeshCore radios and media

- Companion radio settings and supported 1–3 byte path hashes.
- Supported repeater, room-server and sensor discovery, login, status and administration.
- RX logs, trace tools, supported region discovery and channel scoping.
- DM acknowledgments, separate heard-repeat counts and captured-path details with location-aware map views.
- Optional MediaMesh/Radio2 photos and recorded voice clips in DMs and channels, with previews, downloads, retries and cached playback.
- Identity sharing, encrypted identity backups and supported official-client JSON configuration imports.

### Maps and tactical tools

- Online/offline maps and supported tile storage/import.
- Team positions, pins, reports, drawings, routes and optional alerts/geofence monitoring.
- Opt-in, time-limited background position sharing on supported Android devices.
- Supported TAK data packages and optional verified TLS TAK-server connections.

### Setup and usability

- First-start setup for selected services, existing identities/backups and optional client devices.
- Expandable help, a searchable interactive field guide and a GitHub-readable FAQ.
- Consistent network labels, compact phone chat controls and app-aware Android Back navigation, including returning to the mobile sidebar after selecting a destination.
- Meshchat neXt branding, N artwork, application namespace and separate app storage.

Radio2 media, node management and TAK compatibility depend on supported firmware and formats. See the [field guide](docs/guide/README.md) for requirements and privacy limitations. Production signing, repository/reporting URLs and release assets are configured before publication.

The firmware assistant is deferred. Prior source-project history is preserved in [SOURCE_HISTORY.md](SOURCE_HISTORY.md); those version numbers do not describe neXt releases.

### Updates

- Enabled automatic signed-update checks using the independent neXt release identity and GitHub feed. Downloads remain user initiated and Android installation requires approval.
