Android MeshCore transport layer

Scope
The MeshCore connection is opt-in. No MeshCore connection starts on app launch.
The backend module meshchatnext.src.backend.meshcore_transport exposes:
- AndroidConnection(kind, target, context=..., port_index=0, baud=115200,
  dtr=True, rts=False): kind is usb or ble; target must be explicitly selected.
- list_usb_devices / usb_has_permission / request_usb_permission(context, path).
- scan_ble(context, duration=5): Nordic UART candidate addresses and names.
- probe_radio(kind, target, context=...): async app-start and device-query check.

The connection implements meshcore_py's transport contract. Set the reader and
disconnect callback, then use connect/send/disconnect, or pass the connection
into upstream MeshCore(connection). The protocol library owns its own handshake,
command queue and reconnect policy. Build with -PmeshchatnextMeshCore to bundle meshcore 2.3.17 and its pinned optional
dependencies. Ordinary HK builds do not add them. MeshCoreSession in
meshchatnext.src.backend.meshcore_session owns setup/query/close and cleans up the
native transport even after upstream reports disconnection. Neither class
automatically starts a radio or changes Reticulum state. There are no new HTTP
endpoints or UI controls yet.

Isolation
Each MeshCore USB connection owns a port, connection and reader thread; each BLE
connection owns a GATT client, handler thread, timer and event mailbox. The only
shared state is DeviceAccess, a process-local hardware ownership guard. RNode's
usb4a bridge, native flasher and able BLE open paths also use this guard. USB
connections remain real Java objects; a closed file descriptor permits reopen.
Other apps/processes are outside this app-local guard. Scan results are candidates:
RNode can advertise the same Nordic UART service. Never auto-select by UUID.

USB wire framing uses '<' + uint16 little-endian length on writes and '>' on
incoming frames. The parser handles split/coalesced packets and console noise.
Payloads are limited to 300 bytes. Serial DTR/RTS are explicit options; boards
may need different DTR settings. BLE waits for service discovery, MTU and CCCD
subscription before ready. Writes are serialized, acknowledged, bounded by MTU,
and never automatically replayed. Android handles OS pairing dialogs. New-device
PIN pairing still needs validation. Permission denial is surfaced to the caller;
there is no new app UI or automatic permission flow in this layer.

Tests
Host tests:
  python -m pytest --noconftest tests/backend/test_meshcore_transport.py     tests/backend/test_able_android.py tests/backend/test_android_ble_permissions.py
The new suite can also run with unittest. NativeSessionTest is a JUnit4 test.

The normal androidTest MeshCoreRadioTest wraps probe_radio through Chaquopy.
It requires explicit meshcoreTransport and meshcoreTarget instrumentation args;
without them it is skipped. Both the raw transport test and managed protocol
test passed on the OnePlus 9 inside a full, separate APK with Chaquopy. The
managed check includes simulated transport loss, query rejection while offline,
reconnect, and cleanup.

For native-only handset tests, build.py makes a disposable, debug-signed APK
with a separate package ID. Requires SDK platform 35, build-tools 35.0.0, a debug
keystore, javac, and the usb-serial-for-android 3.8.1 classes.jar:
  python scripts/android/meshcore-tests/build.py --usb-jar /path/to/classes.jar
The output directory is printed. No release signing key or installed HK data
is used. Install with adb install -g (or grant Bluetooth permissions explicitly).
Run am instrument -w -r with the component:
  com.haadkoe.meshchatnext.meshcoretest/com.meshchatnext.meshcore.RadioInstrumentation
Arguments:
  -e mode scan          five-second Nordic UART scan and passive USB inventory
  -e mode usb-missing   missing-device error and cleanup
  -e mode ownership    rejection/cleanup against simulated RNode device owner
  -e mode ble -e target AA:BB:CC:DD:EE:FF
                       two fresh BLE handshake/query sessions, no settings writes
The BLE test target must be the explicitly selected MeshCore companion. These
tests do not prove live concurrent RNode/MeshCore operation inside the full app.

Hardware results are saved in outputs/meshcore-android-connection-layer/validation.json.

Full runtime integration build
prepare_integration.py assembles a separate source tree using the existing
verified native-input manifest plus an allowlisted MeshCore overlay. It verifies
the four additional dependency wheels against dependencies.json and writes
meshcore-overlay-provenance.json. Arguments:
  --native-inputs /path/to/verified/native/input/tree
  --frontend /path/to/prebuilt/meshchatnext/public
  --dependencies /path/to/meshcore/wheels
  --dest /path/to/new/build/tree
  --backend-port 8011  # optional: isolates the test UI from installed HK on 8000
The destination must not already exist. Build from its android directory with
MESHCHATNEXT_APPLICATION_ID=com.haadkoe.meshchatnext.meshcoredev and the normal build
Python/SDK environment, then run:
  ./gradlew :app:assembleDebug :app:assembleDebugAndroidTest \
    -PmeshchatnextAbis=arm64-v8a -PmeshchatnextMeshCore
Only arm64 Android has been validated for this feature. Install the app and test
APKs with adb install -g (and -t for the test APK). Run the full-runtime tests:
  adb shell am instrument -w -r \
    -e class com.meshchatnext.meshcore.MeshCoreRadioTest \
    -e meshcoreTransport ble -e meshcoreTarget SELECTED_ADDRESS \
    com.haadkoe.meshchatnext.meshcoredev.test/androidx.test.runner.AndroidJUnitRunner
The test APK is separate from the production HK app and uses separate storage.
The tests initialize the real Application/Python runtime without starting the
WebView or HTTP backend. They do not test full UI startup or live RNode traffic.
Simultaneous RNode testing was explicitly deferred by the user.

Radio settings API (no UI or HTTP routes yet)
Use an explicitly connected MeshCoreSession:
  current = await session.read_settings()
  verified = await session.apply_settings(
      frequency_mhz=906.875, bandwidth_khz=250,
      sf=11, cr=5, tx_power_dbm=22, path_hash_bytes=2)
Omit fields to preserve their current values. Unchanged values do not write flash.
Do not use the example values as a regional preset; read the radio first.

Units and protocol bounds:
- frequency_mhz: 150..2500 MHz, at most three decimal places (1 kHz wire units)
- bandwidth_khz: 7..500 kHz, at most three decimal places (1 Hz wire units)
- sf: integer 5..12
- cr: integer denominator 5..8, representing 4/5 through 4/8
- tx_power_dbm: integer -9 through the radio's advertised max_tx_power_dbm
- path_hash_bytes: integer 1..3, mapped to firmware modes 0..2
Bounds are the companion handler's bounds, not an assertion that every board
supports every value. A firmware rejection or different readback fails the update.

read_settings also returns max_tx_power_dbm, protocol_version, client_repeat,
and path_hash_supported. On older firmware, path_hash_bytes is None rather than
an invented 1-byte default. Missing repeat metadata blocks a radio parameter
write if preserving repeat mode cannot be guaranteed. Client repeat is read-only
in this API and is preserved even when only one radio parameter changes.
TX power handles the parser's unsigned int8 readback and signed wire values.
Exact integer wire encoding avoids float-to-int truncation in the upstream setter.

All requested changes are validated before the first write. Each acknowledged
command is followed by fresh readback. Multiple commands are not atomic: a
SettingsApplyError reports attempted_fields, verified_fields, and best-effort
current_settings (None if unavailable). The normal API does not retry uncertain
writes or silently roll them back. Cancelled writes invalidate cached info.
No identity keys, BLE PINs, contacts or queued messages are exposed or changed.

Hardware settings tests require a second explicit opt-in argument:
  -e meshcoreSettingsWrite true
The opt-in radioSettingsRoundTrip test saves a private recovery snapshot before
writes, changes and verifies all requested fields, cycles supported path hashes,
and restores the original snapshot in finally. It removes the recovery file only
after exact final readback. An unresolved snapshot blocks another write test;
retain the test app and recover the radio before deleting that app if cleanup fails.
The settings round-trip passed on the OnePlus 9 with all hash sizes supported.
Firmware command reference:
https://github.com/meshcore-dev/MeshCore/blob/main/examples/companion_radio/MyMesh.cpp

Debug-only coexistence tests
android/app/src/debug/python/meshcore_runtime_checks.py is included only in debug
builds. It is copied by prepare_integration.py and is not a release dependency.
Select a single instrumentation method with -e class CLASS#METHOD:
- radioDiscovery, with -e meshcoreDiscovery true: filtered Nordic UART discovery.
- coexistenceReadOnly, with -e meshcoreCoexistence true and meshcoreTarget:
  holds MeshCore for 20 read-only queries across a close/reconnect cycle. Monitor
  the existing HK process and RNode through its authenticated interface-stats API.
- sameProcessRadios, with -e meshcoreSameProcess true, meshcoreTarget and
  rnodeTarget: uses RNS's actual Android BLEConnection and the MeshCore client in
  one Python process. Queries RNode firmware only, checks parallel queries and
  independent close in both directions, and verifies MeshCore settings unchanged.

Before sameProcessRadios, release the selected RNode from any existing client.
The 13 test used HK's live /reticulum/interfaces/detach endpoint (configuration
unchanged), then reattached the original interface in finally and verified it
online. Do not open a second RNode GATT client against an in-use radio. The test
requires an explicitly selected paired address and does not reset the adapter.
This proves transport coexistence and independent teardown, not simultaneous
LXMF/MeshCore message delivery. On the OnePlus 13 (Android API 36), both phone-level
and same-process checks passed with RNode 2250 and Seeed Tracker T1000-E v1.18.0.

Messaging backend (opt-in, no UI)
--------------------------------
meshcore_store.MeshCoreStore(path) owns a separate SQLite WAL database in app
private storage. Full companion public keys scope profiles, contacts, receipt
journals and history; neither Reticulum storage nor private identity keys are
used. A single MeshCoreMessaging controller owns its connected MeshCoreSession.
Create a new controller for each connection; close it before replacing a session.

    session = MeshCoreSession()
    await session.connect("ble", selected_address, context=context)
    store = await asyncio.to_thread(MeshCoreStore, private_database_path)
    messages = MeshCoreMessaging(session, store)
    identity = await messages.open()  # public key/name and complete contacts only
    await messages.start_receiving()  # explicitly consume the firmware queue
    row = await messages.send_direct(full_peer_public_key, text,
                                     request_id=stable_unique_request_id)
    history = await messages.history(full_peer_public_key)
    await messages.close()

Command transactions share the radio-settings lock. Incoming messages commit
before fetching the next firmware message. Channel text/data are preserved too,
and channel management uses MeshCoreChannels as described below. Prefix collisions remain unattributed and
block outgoing sends; no arbitrary peer is selected. Exact repeated incoming
content with the same sender and timestamp is deduplicated. The wire protocol
provides no globally unique received message ID, so identical same-second
messages cannot be distinguished. Firmware pops a message before local storage
can commit; an app crash/storage failure in that interval is not recoverable by
this protocol. A storage failure stops further queue consumption.

Outgoing text is validated by UTF-8 byte length (160 maximum). Each submission
is persisted first. Reusing a request ID returns its existing result and never
transmits a second packet. Explicit firmware rejection is 'rejected'; missing
command responses/disconnects are 'unknown' because transmission may have taken
place. No automatic retry, route reset, advertisement or message replay occurs.
'accepted' means the local companion accepted the packet; 'delivered' requires
its expected destination acknowledgement (not a read receipt). Expiry becomes
'unconfirmed' when history is read; late acknowledgements can still confirm it.
Receipt codes are only 32 bits, so collisions never confirm multiple messages.

Debug hardware check: select MeshCoreRadioTest#directMessaging, pass
meshcoreTarget=<paired BLE address> and meshcorePeer=<unique chat contact name>.
Without meshcoreMessageWrite=true it only reads identity/contacts/settings.
With that flag it sends ONE benign test DM requesting a reply, consumes/saves
queued messages, and waits up to 90 seconds for delivery and a peer reply.
Requires an explicitly approved test peer. History remains in the test app's
private meshcore-messages.sqlite; do not uninstall the test app before preserving
any wanted test history. No message content or private keys appear in reports.

Public and private hashtag channels
-----------------------------------
MeshCoreChannels(messages) manages the same explicitly owned companion session.
Call refresh() before start_receiving() to load observed slot bindings. This
reads all slots using the firmware-reported capacity and stores metadata only.

    channels = MeshCoreChannels(messages)
    inventory = await channels.refresh()
    public = await channels.add_public("#local")
    private = await channels.add_private("#friends")  # random 128-bit key
    # Or join with an explicitly supplied 16-byte key:
    private = await channels.add_private("#friends", key=shared_key)
    sharing_key = await channels.export_key(private["slot"],
                            expected_channel_id=private["channel_id"])
    sent = await channels.send(private["slot"], text,
                            expected_channel_id=private["channel_id"],
                            request_id=stable_unique_request_id)
    history = await channels.history(private["channel_id"])
    await channels.remove(private["slot"],
                            expected_channel_id=private["channel_id"])

Names are exact/case-sensitive UTF-8, at most 31 bytes, with a leading # and no
whitespace/NUL. Public channel keys use SHA-256(name)[:16]. Private keys must be
16 bytes and distinct from the name's public key and the well-known Public key;
no passphrase-to-key conversion or sharing URI format is implied. Exporting a
sharing key is explicit. Inventory/history never returns keys. The upstream
set_channel helper changes explicit hashtag keys; our exact command encoder
preserves them. Private key material is held in process memory for protocol
operations; only the full SHA-256 key identity is persisted in metadata/history.
Normal app logging remains INFO; upstream protocol DEBUG logs can contain raw
payloads/secrets and must not be enabled in user builds.

Adding uses the first empty non-default slot, refuses to overwrite configured
slots, and preserves slot 0. Every write verifies name and key by readback.
An uncertain write raises ChannelUpdateError with the slot only; refresh before
another edit. No automatic write retry/rollback occurs. Removing preserves saved
history. Channel identity is the full SHA-256 of the key, not slot/name or the
one-byte on-air channel hash. Same-name channels with different keys stay apart.

Queue draining and edits use the same lock as settings and ordinary receiving.
Packets commit before another is fetched. Before reuse, the old queue is drained;
packets fetched while a slot changes are retained without a channel binding.
channels.history(None) returns these unbound packets. Firmware queue packets
contain a slot index without a channel generation/key: bindings are those
observed at fetch time. Offline queue packets surviving an external channel edit
cannot be reliably assigned retrospectively. Existing pre-channel generic history
remains preserved, without inventing channel keys for it. Channel sender names
are part of plaintext display text, not authenticated contact public identities.

The outgoing text limit includes the firmware-added '<radio name>: ' prefix,
preventing firmware's silent UTF-8 truncation. A channel packet's 'submitted'
state means local radio acceptance, never confirmed recipient delivery. There
are no channel destination acknowledgements. Repeated request IDs never resend;
missing responses become 'unknown', explicit firmware errors 'rejected', and
stranded submissions become 'unknown' on restart. Binary channel data is retained
when received but binary sending is deferred. Datagrams without a timestamp are
retained individually; equal data is not collapsed forever.

Hardware: MeshCoreRadioTest#channelRoundTrip requires meshcoreChannelWrite=true,
meshcoreTarget=<T1000-E BLE address>, meshcorePeerTarget=<TestPeer BLE address>.
Both radios must have an empty non-default slot. It checks distinct identities
against their mutually added contacts, sends a public and private round trip,
checks persisted incoming history, removes only its temporary channels, and
verifies both complete channel inventories and radio settings match baseline.
An app-private recovery file is written before changing the originally empty
slot. Failures retain recovery data; fixtures refuse unresolved snapshots.
No configured existing slot is overwritten. The test app retains its history.

Identity, recovery, and application integration
----------------------------------------------
MeshCoreSession.read_identity() returns only name/full public key. set_name()
validates 1-31 UTF-8 bytes, verifies public key + name readback, and does not
advertise. backup_identity(password, expected_public_key=...) explicitly exports
the firmware's 64-byte expanded Ed25519 key and returns an encrypted object.
It never stores a plaintext key or silently exports one during connection.
Firmware-disabled import/export returns a distinct PermissionError.

Backups use format meshchatnext-meshcore-identity-v1: AES-256-GCM, random 16-byte
salt/12-byte nonce, scrypt N=16384/r=8/p=1, with format/public key authenticated
as additional data. Passwords require 12-1024 characters. This is a Meshchat neXt
backup container, not a standard Ed25519 seed file or an official-client export.
MeshCore uses an expanded private scalar; the matching public key is derived
and checked before encryption and before any import. No crypto dependency is
imported on the ordinary non-MeshCore application path. Python cannot guarantee
secret-memory zeroing; plaintext exists in process memory during explicit key
operations, and upstream protocol DEBUG logging must remain disabled.

restore_identity(..., expected_current_public_key=...) checks the selected radio,
authenticates the backup, imports once and verifies the new public identity.
Restoring an already active public identity is a no-op. MeshCoreService.restore()
is the application-level entry point: queued messages are committed to the old
account, receiving is stopped, the import is not retried, and workers are rebuilt
under the verified restored identity. Firmware packets lack an identity epoch;
queued traffic racing an externally changed identity cannot be reconstructed
retrospectively. Restore errors stop the connection for inspection/recovery.

MeshCoreService owns one independent session, messenger, channel manager, and
history database under storage_dir/meshcore (not an LXMF identity directory).
Its lifecycle is registered on the web application's startup/shutdown; ordinary
builds without the optional meshcore package remain unavailable. Construction
starts no radio. No saved explicit selection means no automatic connection.

POST connect selects an exact BLE address/USB path. Successful selections save
only target, transport, receiving/reconnect choices and the verified public key.
Unexpected link loss or failed receive processing creates fresh native/protocol
sessions with bounded exponential reconnect delay, up to 30 seconds. It never
replays settings, messages, advertisements, key imports, or outgoing packets.
A different identity at the selected target blocks recovery before history or
queue processing starts. Explicit connect adopts the selected radio afresh.
Explicit disconnect clears the persisted selection and stops reconnection.
Service close retains a successful selection for restart recovery. Receiving
is opt-in (connect's receive defaults false); it is restored only when explicitly
enabled. Persisted configuration writes complete before cancellation releases
lifecycle locks. RNS reloads/identity switches do not own this service or its DB.

API prefix /api/v1/meshcore, behind existing application auth/CSRF/IP/demo guards:
GET status, identity, settings, contacts, channels, history, channel-history.
POST connect, disconnect, receiving, name, backup, restore, settings, message,
channel-add, channel-remove, channel-key, channel-message.
Writes accept JSON objects capped at 16 KiB with strict per-action field sets;
unknown actions/GET backup are not supported. Responses are no-store. Exceptions
never echo passwords, keys, payloads, or raw upstream exception text. The API
uses the same existing application authentication readiness policy as other
protected endpoints; it does not bypass login while an LXMF context initializes.
See meshcore_http.py for each action's required/optional fields. Normal routes
require no UI changes and no optional MeshCore import to register.

Hardware check: MeshCoreRadioTest#identityAndRecovery with
meshcoreIdentityWrite=true and meshcoreTarget=<paired BLE address>. It uses an
empty separate service-test folder/history, temporarily renames the radio with
an app-private original-name recovery snapshot, checks encrypted backup if
firmware permits export, verifies same-identity restore without importing a
replacement key, restores the name, forces transport loss, checks a fresh
connection, recreates the service from disk, then checks manual disconnect.
It sends no LoRa messages and verifies original public identity/settings. Host
monitoring checks the original HK PID/config and RNode availability throughout.
This does not claim an OS process-kill/Doze test or a physical USB-unplug test.

Forced idle and actual process-death recovery (instrumented)
----------------------------------------------------------
MeshCoreRadioTest#backgroundPrepare and #backgroundResume require
meshcoreProcessTest=true; prepare also needs meshcoreTarget=<paired BLE address>.
meshcore_background_checks.py uses a separate private test folder, no receiving,
and an explicit transport read-command allowlist. It stages a local outgoing
submission without invoking a send API. No radio settings, identity, channel,
advertisement, or LoRa-send commands are permitted through this test transport.

The host waits for progress.json, records the original idle force state, enters
forced deep idle for a bounded 20-second window, verifies Android reports IDLE,
then unforces idle and verifies query progress resumes. It kills only the debug
package's exact PID under its own UID. The resume test runs in a newly observed
PID, starts from the persisted selection, verifies identity/settings unchanged,
and checks the interrupted submission is retained as 'unknown', never replayed.
A manual disconnect clears the test selection afterward. The original HK PID,
configuration digest and RNode stats are monitored; the ordinary MeshCore client
is reopened and idle force controls are restored in finally. No battery spoofing,
battery exemptions, global Bluetooth resets, or original-HK process termination
are used.

This proves behavior under forced deep idle while Android instrumentation/ADB
is active, plus recovery on a fresh process's startup after an actual process
kill. Instrumentation can affect scheduling; this is not a long unattended
battery/Doze survival test or proof that Android automatically relaunches a
killed app. Physical USB-unplug testing remains deferred by user request.

First conversations/contacts UI pass
------------------------------------
MeshCore threads are separate, explicitly labelled rows within the existing
Conversations sidebar. Their reader/composer is independent of LXMF, and route
query meshcore=<full public key> is separate from the RNS destinationHash route
parameter. Switching to MeshCore unmounts hidden LXMF viewers and clears their
open-destination notification context, preserving Reticulum unread status.
Collapsed sidebar and phone-width layouts retain MeshCore access/labels.

Contacts include standalone MeshCore chat contacts and optional explicit links
to an existing Reticulum contact. Same display names never create a cross-network
link. Links are stored by MeshCore owner, local Reticulum account and contact ID;
changing accounts clears stale frontend link state. Database writes are guarded
by the UI's expected MeshCore owner, preventing an old draft/link selection from
being applied after the radio identity changes. Unlinking preserves both contacts.
Saved contacts/history can be viewed while the radio is disconnected.

Add Contact provides a network selector. MeshCore additions accept a full 32-byte
public key as 64 hex characters plus a name, create a flood-routed chat contact
on the radio, and verify a fresh contact snapshot. RNS-only contact actions are
not shown for standalone MeshCore entries. The context menu distinguishes
Message via Reticulum and Message via MeshCore. Linking lives under the RNS
contact's disclosure and requires selecting a MeshCore contact and pressing Link.

GET /api/v1/meshcore/ui returns cached contact/thread snapshots and, when peer is
provided, up to the latest 1000 saved direct messages. POST contact-add accepts
peer/name, contact-link accepts contact/peer (null peer unlinks), and read accepts
peer/through. These writes and message accept an optional expected_owner guard;
the frontend always sends it. Contact links require an existing contact ID in
the active RNS account, except unlink also permits clearing an orphaned link.
Read markers apply only through the displayed message timestamp, preserving later
incoming messages and other peers' unread state. Thread send retries reuse the
same request ID when a response is lost. There is no automatic outgoing retry.

The first UI pass polls cached snapshots every four seconds, stops on unmount,
and keeps connection setup in a small disclosure. Bluetooth selection currently
uses an explicitly entered paired-device address; USB uses a device path. A
friendly radio picker, MeshCore announces, channel sidebar, and global incoming
notification delivery/muting remain separate follow-up work. Existing firmware
contacts are synchronized on connection or explicit contact changes; this pass
is not a live announces browser. New UI strings currently use English.

Branding: the startup screen and existing Meshchat neXt name are temporary. The user plans a complete rebrand; branding changes are deferred until after the network UI work.

UI follow-up: extend the existing Share My Identity dialog with explicit Reticulum and MeshCore identity choices, each clearly labelled. Preserve the current app styling and existing Contacts navigation.

Announces UI pass:
- The existing Announces tab now has Reticulum/MeshCore buttons, with separate searches, filters and retained list elements/scroll state.
- Reticulum keeps its address-keyed rows; the ordering no longer caches an obsolete timestamp after a repeat announce.
- MeshCore ADVERTISEMENT and NEW_CONTACT pushes feed identity-scoped SQLite discoveries. Repeat events update the existing public-key row. Pending bursts coalesce by key; known-device events read contact metadata over the companion link without transmitting an advert or message.
- New discoveries do not create app contact links. Client rows offer Add Contact or Message via MeshCore; repeaters and rooms are labelled without client messaging actions.
- Saved discoveries remain available offline. Local receipt times are labelled Last heard; timestamps seeded from the radio contact table are labelled Advertised. The companion notifications used here do not provide per-device RSSI/SNR, so signal figures are omitted. Outbound route details are labelled Route rather than inferred receive hops.
- MeshCore discovery polling runs while Announces is open. The existing virtual list handles larger lists. The isolated sample-data review now includes clients, a repeater and a room server.
- Validation: 99 frontend tests, 91 backend tests plus 26 subtests, frontend production build, ESLint, Ruff and diff whitespace checks pass. Live radio announce verification and an Android UI build/install remain pending.

Channels, nodes and local channel banishment UI pass:
- Both classic and grouped navigation accept the MeshCore insertion below Relay Chat (Contacts fallback when Relay Chat is hidden). Channels and Nodes expand independently; collapsed entries open their overview pages.
- Channels list public/private icons, per-channel unread counts and mute preferences; the parent sums unread counts, including muted channels. Local read markers/mute preferences are keyed by companion identity and cryptographic channel ID, not mutable slot number.
- Channel pages provide offline saved history, guarded stable-ID sends, UTF-8 limits including the radio-name prefix, public hashtag creation and private channel joining/creation. Private keys remain transient; sharing/export UI is deferred. Radio slot/channel-ID readback prevents sending to a reassigned slot. No sends are retried automatically.
- Save Node on repeater/room announces adds a local saved-node entry and details view. These nodes are separate from Contacts and do not send login or management commands. Repeater management and room-server messaging are deferred.
- Incoming channel messages offer a three-dot Banish sender name action. This is a reversible, local, exact displayed-name filter scoped to the channel. Companion channel text does not contain a verified sender public key. A name change can evade the filter; it does not remove a peer from the radio network. Filtered messages are retained but excluded from channel history/unread counts, and lifting the filter restores visibility. Banishment shows a clearly labelled MeshCore section with search/sort and per-row lift actions; Reticulum bulk actions remain explicitly labelled.
- Background snapshots preserve channel drafts, open menus and selected contact links unless the underlying identity changes. Read-marker writes do not recursively refresh history.
- The sample-data browser review verified hide/lift/restore, saving/opening a repeater, channel navigation and unread clearing. These browser actions use an in-memory API and never transmit on LoRa.
- Validation: 121 frontend tests across nine suites, 95 backend tests plus 26 subtests, production frontend build, ESLint, Ruff and whitespace checks pass.
- Global MeshCore OS notifications, including honoring stored per-channel mute preferences in notification delivery, remain a separate follow-up. No Android UI APK was installed or new UI live-radio test performed in this pass. Physical USB unplug testing remains deferred by the user.

MeshCore notification delivery pass (supersedes the earlier global-alert follow-up):
- Fresh, committed incoming direct/channel text produces an identity-scoped meshcore.message event. Duplicate packets and binary channel data do not alert. Alert failures never fail radio reception; a separate bounded worker coalesces bursts by conversation/channel. Historical messages are not replayed as alerts after reconnect/restart.
- The worker rechecks local read state, channel mute preferences and displayed-sender banishments before dispatch. Unread counts/history remain independent of mute. Keys are namespaced SHA-256 of the full companion identity, message kind and peer/channel identity; no Reticulum destination shares the same notification key.
- Android uses the existing native Python/Java notification bridge, so an open WebView/socket is not required for OS delivery. The frontend does not also play sounds/show OS alerts on Android. Existing Android message channel/permission controls apply. Titles begin MeshCore; channel titles include the hashtag and bodies retain the displayed sender prefix.
- The native bridge now checks MainActivity foreground state specifically for MeshCore open-view suppression. A stale open-channel key in a suspended WebView cannot suppress background alerts. Existing Reticulum open-hash behavior is unchanged.
- Browser/Electron dispatch follows existing foreground sound, background OS-toast and Do Not Disturb rules. Viewing a MeshCore thread/channel in a focused visible window clears its OS alerts; leaving that view releases its context. MeshCore and Reticulum context keys coexist in the Android bridge. OS notification taps retain the existing app-focus behavior.
- Notification tests cover fresh-only delivery, duplicate suppression, namespace isolation, read/mute/ban policy, burst coalescing, sink failures, DND/open-view suppression, network labels, Android ownership, independent RNS/MC context and release on channel overview navigation.
- Validation: 167 frontend tests across 13 suites; 99 backend tests plus 26 subtests; five native Android JUnit checks; production frontend build; ESLint/Ruff/whitespace checks pass. The native Java sources/tests were copied into the existing prepared Android test tree to use its already-verified build assets; a raw source-tree run stopped on absent packaged visualiser assets. No test was skipped in the prepared-tree run. No APK was installed or live OS notification/radio round trip performed.

Additional notification isolation check: the existing Android push-bridge suite passes all 27 tests, including a new check that only MeshCore keys use the native activity-foreground guard. Combined Python validation is 126 tests plus 26 subtests; frontend remains 167 tests, native Android remains five JUnit tests.

Full UI coexistence builds use --backend-port 8011 and the separate meshcoredev
application ID. The generated test checkout alone changes MainActivity, the local
backend URL and native audio URL; the source checkout retains its production port.
The chosen port and generated hashes are recorded in overlay provenance. This
prevents a second app WebView from accidentally using the existing HK backend.

Handset UI notification validation (2026-10-24): the isolated meshcoredev
app on the OnePlus 13 received a fresh direct message from the selected
TestPeer peer and Android posted "MeshCore · TestPeer". A live
Public-channel message also posted "MeshCore · Public". The handset was
locked when checked. The existing HK/RNode interface remained online.
Mute and open-conversation clearing checks are tracked separately in
outputs/meshcore-ui/phone13/validation.json; do not infer them from alert delivery.

The subsequent live Public mute check passed: two new unread messages arrived,
including the selected TestPeer peer, without updating the existing Android
channel notification. The original mute preference was restored. Opening the
peer conversation in the actual handset UI reduced its unread count to zero
and removed its direct-message notification. The original RNode remained online.

MeshCore radio settings UI
The standalone MeshCoreSettings component is mounted under Settings > Network
(Advanced), reachable directly from the MeshCore conversation-list shortcut.
It can later be moved to Interfaces without changing its behavior. Android paired
BLE candidates are read by GET /meshcore/bluetooth-devices, without opening any
GATT client or changing adapter state. Names and addresses appear in a dropdown;
manual entry remains available. Classic-only devices are excluded; BLE RNodes
may still appear and must never be selected automatically.
Radio settings automatically read from the connected companion; live configured
values take precedence over sample values. Poll updates preserve drafts. Writes
contain changed fields only and expected_owner. Uncertain results require a new
read before retrying. Unsupported path hashes cannot be changed. No regional
preset is automatically written to a radio.
The user's current T1000-E profile read on 2026-10-24 is 910.525 MHz, 62.5 kHz,
SF7, CR 4/8, TX 22 dBm, 1-byte path hashes. The sample preview uses this profile.

Public identity sharing UI
The existing Contacts > Share My Identity dialog has explicit Reticulum and
MeshCore choices. Reticulum remains the initial selection and retains its URI
and QR behavior. MeshCore shares the selected owner's 64-character public key
as raw text/QR, not a claimed official-client URI format. The radio display name
and live/offline identity state are labelled separately. No private-key export,
backup or identity-import endpoint is called by this view. Async QR results are
invalidated immediately when the owner changes. Clipboard/share payload tests
verify public-key-only output, offline labeling and cancellation handling.
Private-key backup/restore management is provided separately in MeshCore settings;
the public sharing dialog never accesses it.

MeshCore identity-name editor
The radio settings panel includes the current MeshCore public address and an
explicit display-name editor. Name changes carry expected_owner, are limited to
1-31 UTF-8 bytes without NUL, and require backend readback of the same name and
public key. No Reticulum config or private key is modified. Polls preserve drafts;
owner/disconnection changes clear them. Failed reads disable editing, and an
uncertain name update requires a fresh identity read before another save.

The name editor live check passed on phone13/T1000-E: a temporary name was
written and read back, then the original name restored and verified. Public
identity and all radio settings were unchanged; RNode was online before and
after. Results: outputs/meshcore-identity-editor/validation.json. Saved-radio
status uses a separate connection kind/target object while preserving the legacy
selected boolean; the UI guards against malformed connection metadata.

MeshCore backups and official companion configuration import
Settings includes encrypted identity backup export and a JSON import preview.
The official companion schema supports identity (expanded 64-byte private key),
radio name, frequency/bandwidth/SF/CR/TX power, contacts and unscoped channels.
Frequency is converted from kHz to MHz and bandwidth from Hz to kHz. Existing
contact keys/channel keys are kept; imported contacts never link to Reticulum
contacts automatically. Contact capacity, channel conflicts, available non-default
slots and actual TX limits are checked again immediately before applying.
Position policy, auto-add policies, region keys/scoped channels, cached paths,
aliases and other unsupported preferences are reported rather than silently
translated. A scoped channel is never downgraded to an unscoped channel.
Nothing is selected automatically. Identity replacement requires explicit user
confirmation and runs last. Changed radio/name/key operations use readback.
An interrupted import stops with its completed sections retained; durable UUID
receipts prevent replay and can be checked through a read-only endpoint. Source
JSON/password/private keys/channel keys are not saved in import receipts/logs.
Exports contain only the existing authenticated encrypted identity envelope.

Phone13/T1000-E validation (2026-10-24): an existing official export preview
recognized 168 contacts and 24 channels without applying that export. An import
of identical name/radio settings and empty contact/channel lists completed;
receipt replay returned the prior result. A temporary private channel with an
arbitrary name was imported and removed; the original channel table was restored.
Encrypted identity export was decrypted and matched locally, without replacing
the identity or saving its private key. Identity/radio settings stayed unchanged,
and the original app's RNode was online before and after. The native download
save-picker interaction and real identity replacement were not live-tested.
Results: outputs/meshcore-backups/validation.json and live-result.json.
Format references (schema facts only; no third-party implementation copied):
https://files.liamcottle.net/MeshCore/Documentation/MeshCore_Quick_Start_Guide.pdf
https://github.com/pelgraine/Meck-P4/blob/main/components/meshcore/MeckExport.h
https://github.com/pelgraine/Meck-P4/blob/main/components/meshcore/MeckImport.h

Channel mentions and reply UI
Channel notifications have All messages / Mentions only / Muted choices. The
new identity/channel-scoped mentions_only column migrates old databases without
changing their existing mute state. Both Android and desktop alert delivery use
the backend policy; muted, read and banished messages cannot bypass it. Mention
matching uses exact bracketed @[Display name] tokens (Unicode NFC/case-insensitive)
in the message body, excluding the sender prefix. The current local radio name
is updated after verified edits/imports. Messages and unread counts are retained.
The notification worker filters before coalescing so an ordinary follow-up does
not replace a queued mention. DMs keep their prior notification behavior.
Channel message actions include Reply to sender, inserting the bracketed mention
before an existing draft and focusing the composer; it never sends automatically.
This is a channel reply addressed by name, not a private message or threaded
room-server implementation. Names containing closing brackets/newlines cannot
be safely represented and are rejected by the reply action.

Server nodes initial implementation
Saved MeshCore Nodes expose explicit login/logout and status requests. Login
callbacks are registered before transmission; only a matching, unambiguous
six-byte contact prefix can confirm a response. Passwords are transient, local
verified login expires after five minutes and resets with the radio connection.
Uncertain server requests block further exchanges for that peer until reconnect;
no automatic retry or stored-password login is performed. Receive processing can
continue while waiting for server responses (the wire lock is held only for the
command, not the 30-second response wait). No administrative CLI writes exposed.
Room posts reuse durable message IDs/receipts with an explicit kind-3 destination
check and verified login. They do not become client direct-message conversations.
Room history displays signed-plain posts (txt_type 2) and server-provided author
prefixes, not CLI text or claimed full author identity. Room unread markers and
foreground notification context use the existing identity/peer-scoped policy.
Room-server hardware is not available for live testing yet; local tests cover
correlation, denial, timeouts, secret clearing, room authorization/history and UI.
Results: outputs/meshcore-nodes/validation.json.
