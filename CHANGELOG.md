# Meshchat neXt changelog

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
