# Meshchat neXt · User guide

User guide for Meshchat neXt 0.1.2, reviewed on 27 October 2026. Features vary by platform, firmware and peer application.

## One app, independent services

Reticulum → RNode / LAN / TCP → LXMF messages and LXST calls.

MeshCore → separate companion → DMs, channels and TAC; optional Radio2 media.

SIP → separate provider account → IP extension calls.

Contact linking groups addresses; it does not bridge networks.

## Install an Android app update

neXt verifies official updates before handing the APK to Android. Downloading an update and installing it are separate steps.

### How to

1. Open Settings → App features → Updates and check for updates. Download the APK offered for your device.
2. After verification, neXt opens Android’s installer. If Android asks whether neXt may install apps, allow it for neXt and return to continue.
3. Review Android’s update confirmation and choose Update. Your existing app data stays in place. Cancel leaves the installed app unchanged and the verified download available to retry.
4. If you return later, tap Install update. Save update file remains available if you prefer opening the APK yourself from Downloads.
5. Reopen neXt after installation. Keep the existing app installed when updating; uninstalling can remove your data.

### Keep in mind

- Android approval is always required; neXt does not silently install updates.
- The installer rechecks the file, app identity, signing certificate and version before opening Android’s confirmation.
- Updates preserve the existing Android permission for full-screen incoming SIP calls. A user who has not allowed it can enable it from SIP settings.

## Start here: one app, separate networks

Meshchat neXt puts several communications tools in one place. You can use just one or combine them. Combining the screens does not combine their networks, accounts or radio protocols.

### How to

1. Install the APK matching your Android architecture: ARM64 (64-bit ARM), ARMv7 (32-bit ARM), or x86_64 (64-bit Intel/AMD). Android 7 or later is supported; SIP calling requires Android 9 or later.
2. Choose what you actually need: Reticulum, MeshCore, SIP, or any combination. You can change the visible features later in Settings → App features.
3. For Reticulum, choose a network interface: internet TCP, local network, an RNode radio, or several. For MeshCore, connect a separate companion radio. For SIP, supply your provider account.
4. Check the network label before messaging, sharing an identity or calling. The same person can have several unrelated addresses.
5. Use Settings → App features → Run setup guide if you leave first launch. The setup Back button returns through setup; Set up later is the explicit way to finish early. Expand the Help tiles for each choice.

### Keep in mind

- On phones, choosing a page from the sidebar makes Back reopen that sidebar first. Back closes dialogs and local panels before leaving a page; closing a reopened sidebar does not trap you in a loop. Android Back and the app Back controls follow the same order.
- Reticulum and MeshCore do not automatically bridge messages. Linking contacts only groups their addresses in your address book.
- TAC is a map/team workflow carried over MeshCore; it is not another general-purpose radio network. SIP is separate internet telephony.
- Feature visibility switches do not stop an already running service. Disconnect or disable it through its own controls.

## Choose your starting path

Start with the equipment and experience you have. There is no requirement to buy two radios or join every service.

### How to

1. No radio yet? Try Reticulum over TCP. During setup choose Internet · TCP; the preferred editable preset is rmap.world:4242. A working internet connection is required.
2. Already use Reticulum? Keep or import your private identity, then add the interfaces you use. A public contact address is not an identity backup.
3. Already use MeshCore? Keep the companion’s existing identity and configuration, or preview a recognized backup. Stop the other app’s connection to that companion before connecting neXt.
4. Want team maps? Establish ordinary MeshCore text messaging first. Then configure a private team channel in Map. Add Radio2 only for supported media features.
5. Want extension calls? Enable SIP, add your own provider account under Settings → SIP, then use Telephone. No radio is required.

### Keep in mind

- A LoRa board’s firmware determines its role. A MeshCore companion and an RNode are not interchangeable just because their hardware looks similar.
- Firmware flashing assistance is deferred. This guide points to external firmware sources; neXt does not yet choose or flash the correct build for you.

## Names, addresses and private keys

A display name is a readable label. An address identifies a destination. A private key lets a device act as that identity. Keep those concepts separate.

### How to

1. For a new Reticulum setup, keep the locally created identity and choose a display name. Reticulum does not require a central account signup.
2. To keep an existing Reticulum identity, import your own raw private identity file or supported Base32 export. The old neXt identity is retained separately; activation may require a restart.
3. For MeshCore, the companion radio owns its identity. Read it after connecting. Importing a private identity into the wrong companion can change who that radio represents.
4. When sharing a contact, choose the network in Share My Identity. Share the public address/card, never your private-key export.
5. Use a SIP extension and provider password only for SIP. They are not Reticulum or MeshCore keys.

### Keep in mind

- Matching names are not proof that two identities belong to one person. Link contacts only after you choose to.
- Back up keys before firmware changes. A lost private identity cannot be recreated from its public address.
- A cloned identity active on several devices can produce confusing routing and state. Do not casually copy keys between simultaneously active radios.

## Reticulum: messages across different transports

Reticulum is the networking layer. neXt uses LXMF for messages and LXST for calls. An interface is the connection that carries Reticulum traffic: radio, LAN or an internet link.

### How to

1. Enable Reticulum in App features and open its setup section.
2. Choose internet TCP, local discovery and/or a separate RNode. Existing interfaces are kept. You can inspect them later under Interfaces.
3. Wait for reachable users and services under Messages → Announces → Reticulum. Setup accepts ordinary announces from enabled outbound TCP interfaces while preserving private boundaries.
4. Save a reachable user as a contact, or exchange addresses. Send a small text first before trying larger attachments or calls.

### Keep in mind

- Reticulum does not need the public internet when a usable local/radio path exists. Adding TCP does not turn MeshCore traffic into Reticulum traffic.
- Announces are discovery advertisements, not messages, delivery receipts or a global directory. Availability depends on your connected network.
- Protocol background: Reticulum manual. neXt’s menus and setup behavior are specific to this build.

## Connect through the internet or your local network

An internet entry point provides a path into Reticulum. Local automatic discovery finds Reticulum devices on the same reachable LAN. Neither option needs a LoRa radio.

### How to

1. In first launch select Internet · TCP to add/reuse rmap.world on port 4242. Expand Server details to change the host or port.
2. Select Nearby devices on the same network for LAN discovery if desired. Both peers need access to that local network; guest Wi-Fi/client isolation may block them.
3. After setup, inspect Interfaces. Check connection state before assuming a lack of announces means the app is broken.
4. For an existing manually configured TCP interface, check whether bootstrap-only filtering is appropriate. First-launch reception setup removes that filtering from enabled outbound TCP connections; it does not remove private interface boundaries.

### Keep in mind

- TCP uses the device’s available internet route. It does not register a SIP account or connect a MeshCore companion.
- The preset is a preferred entry point, not a guarantee that every Reticulum user or service is reachable.
- Advanced Tor/I2P interfaces depend on their own transports and configuration. They are not created merely by enabling a feature checkbox.

## Connect an RNode for Reticulum

An RNode is a radio modem for the Reticulum side of neXt. It is configured independently of the MeshCore companion—even if both are attached to the same phone.

### How to

1. Confirm the exact board is running suitable RNode firmware. Keep its existing settings/backup before any firmware work; the firmware assistant is not included yet.
2. For Bluetooth, pair in the system settings and choose Bluetooth LE unless your RNode needs Classic. Refresh paired radios and choose your actual RNode, not a MeshCore device in the same list.
3. For Android USB, use a data-capable OTG cable and grant USB access. For RNode over IP, supply the reachable RNode endpoint.
4. Check frequency, bandwidth, spreading factor, coding rate and transmit power with your local Reticulum group. New-form defaults are 914.875 MHz, 125 kHz, SF8, CR4/7 and 17 dBm; they are not worldwide defaults.
5. Use Add RNode connection. Check Interfaces and test a short Reticulum message. Existing matching RNode interfaces are kept rather than overwritten.

### Keep in mind

- A paired Bluetooth device is not necessarily connected. A connection is not proof of radio reachability.
- Radio parameters must match compatible peers and remain appropriate for your region and hardware. Power limits vary.
- Sidebar battery readings may be approximate or voltage-based. They are not calibrated guarantees of remaining runtime.

## Send LXMF messages and use propagation

Messages labelled Reticulum use LXMF. LXMF peers in other applications can exchange compatible messages when addresses, routes and supported content formats match.

### How to

1. Open a Reticulum contact or select a Reticulum announce. Verify the network label and send a short text.
2. Use the conversation composer for supported images, audio and files. Large payloads take longer on low-bandwidth links.
3. If a peer is offline, configure an appropriate propagation node under Tools → Propagation nodes or the related Reticulum settings. Sync to collect messages held for you.
4. Review delivery state rather than assuming that an entry in your local conversation means the recipient received it. Investigate stamp requirements and routes when a send fails.

### Keep in mind

- Propagation is encrypted store-and-forward delivery, not an instant connection or a universal global inbox. Reachability and configuration still matter.
- Sideband, NomadNet and other LXMF clients share the messaging ecosystem; their rich-content and UI features can differ. Test plain text before relying on a specific attachment format.
- Reticulum/LXMF addresses are not MeshCore public keys. Do not paste one into the other network’s address field.

## Make a Reticulum call with LXST

LXST telephone calls are live Reticulum calls. They are distinct from SIP calls and from recorded MeshCore voice clips.

### How to

1. Enable the Reticulum telephone function in Reticulum settings. Check microphone and notification permissions on the device.
2. Use Telephone or a callable contact that advertises a compatible LXST telephone destination. A messaging address alone does not establish call compatibility.
3. Place a call and ask the other person to answer. Try headphones and a reliable link first.
4. Use mute, hang up, and the available full/half-duplex controls. Half duplex with push-to-talk can reduce idle airtime on constrained paths.
5. If using voicemail, greetings or recordings, review the telephone settings and local storage/privacy implications.

### Keep in mind

- An app that supports LXMF text does not automatically support LXST telephone.
- Live audio depends on usable bandwidth, loss and latency. It is not a promise of telephone-quality speech over every LoRa path.

## Connect a MeshCore companion

A companion/client node connects your phone to a MeshCore radio network. Repeaters extend coverage, room servers host conversations, and sensors provide supported data/services; they are not substitutes for your local companion.

### How to

1. Check that your exact device has companion firmware for the intended connection. BLE and USB companion builds can differ. See the official MeshCore releases; choose the precise board/module.
2. For BLE, pair in Android settings, close other apps using the same companion, then Settings → MeshCore → Refresh paired radios → select it → Connect.
3. For USB, attach a supported USB companion through OTG, refresh USB radios, choose the device, allow Android access and connect.
4. Read the identity and existing radio profile before changing anything. The node’s saved settings take priority.
5. Check Messages → Announces → MeshCore and send a small DM to a known reachable peer.

### Keep in mind

- neXt can run this companion alongside an independent RNode. That is two connections to two separate systems.
- After USB re-enumeration, refresh/select/connect may be required. Check the cable and power arrangement before repeatedly reconnecting.
- A connected companion can still be unable to hear your local mesh if its primary radio profile differs.

## Understand frequency, BW, SF, CR and path hashes

Radio settings describe how signals are transmitted and received. Change them deliberately with your local group’s guidance; values suitable for one region or network may fail elsewhere.

### How to

1. Read the current radio settings. Check frequency (MHz), bandwidth (kHz), spreading factor (SF), coding rate (CR) and transmit power (dBm).
2. Match the primary radio profile to the MeshCore group you intend to reach. The unset-value fallback in this build is 910.525 MHz, BW62.5 kHz, SF7, CR4/8. The separate Use Puget Mesh preset action selects CR4/5. Read your node’s saved profile first; power must respect the hardware and local limits.
3. Select a supported default path hash size from 1 to 3 bytes. This controls repeater-hop identifiers; it is not a region name length or encryption strength setting.
4. Apply and read back settings. If radio communication disappears, compare both endpoints’ profiles before blaming contacts or passwords.
5. Keep Radio2’s media profile separate from the primary mesh profile. Matching the two is not a general requirement.

### Keep in mind

- RNode new-setup defaults belong to Reticulum. Do not automatically apply them to the MeshCore companion.
- Saved radio settings are preferred over presets. Transmit power may be limited below the form’s fallback value.
- A repeater’s saved path can become stale. Direct/zero-hop route discovery is separate from successful login.

## Send MeshCore DMs and understand send states

MeshCore DMs appear in the shared Conversations area with a MeshCore label. The shared screen does not convert them to Reticulum messages.

### How to

1. Open a MeshCore contact, or add a user from MeshCore announces. Check the public key and network label.
2. Send a short text and inspect its state. A DM acknowledgment and the number of heard repeats are separate observations.
3. For a linked person, choose the MeshCore messaging action explicitly. Their Reticulum conversation remains its own thread.
4. Use the media controls in the DM composer for supported photos and recorded voice only after Radio2 setup is working.
5. Choose Details on a message to inspect captured paths, signal readings and outgoing repeats. Known short-hash matches can be ambiguous. View captured paths or reported client locations on the map when available; missing hops are not joined.

### Keep in mind

- Heard repeats count matching retransmissions observed by your client, not unique repeaters or proof of delivery. Missed packets while disconnected cannot be reconstructed.
- Channels do not use recipient delivery receipts. A channel message accepted by the radio is not confirmed as read or received by everyone.
- Notifications identify MeshCore. Open a notification to reach the relevant conversation; channel navigation aims at the first unread message.

## Create, manage and follow MeshCore channels

A hashtag channel is a shared conversation identified by its name-derived key. A private channel uses a shared key. A channel is different from a room server.

### How to

1. Expand MeshCore Channels and open its manager. Add a public hashtag by name or a private channel with its shared key.
2. New public hashtag names are normalized to lowercase for compatible name-based joining. For an older mixed-case channel, exchange the exact key; changing the displayed name alone does not change that key.
3. Use the arrow controls to reorder channels. Drag-and-drop is not required. Hide a channel to remove it from the normal list, and show hidden channels in the manager to unhide it.
4. Delete a channel from the manager when appropriate, including Public if you do not want it. Review the deletion prompt; hiding is the reversible choice when you only want less clutter.
5. Choose All messages, Mentions only or Muted per channel. The sidebar shows per-channel unread counts and a parent total.

### Keep in mind

- Anyone who has a channel key can participate. A public hashtag’s key is not a private invitation.
- Banishment hides a sender locally. It does not ban them from the radio network or other people’s clients.
- Use a temporary private test channel for repeated experiments, rather than filling a neighborhood public channel with tests.
- The compact chat header keeps notification mode controls; channel scope stays in Manage channels. Use the attachment row’s Photo or Voice clip button to open its scrollable editor.

## Reply to a person and control notifications

Replies insert a mention into a channel message so the intended person is clear. Notification preferences are local to your app.

### How to

1. Use Reply on the chosen message. Keep the inserted mention and type your response.
2. The mention form is @[Display name]. Spaces and emoji matter; Reply is easier than retyping a long name.
3. Set the channel to Mentions only to suppress ordinary message alerts while still alerting on a matching mention of your companion’s name.
4. Select Muted to suppress all channel message alerts, including mentions. Messages remain in the conversation and still contribute unread state.
5. Check Android notification permissions and Do Not Disturb if an expected alert is silent.

### Keep in mind

- Names and mentions do not authenticate the sender. Changing your companion’s name changes which name mentions match.
- Room-server/tactical alert controls can have their own settings; a chat mute is not a universal stop switch for every map event.

## Keep people together without merging networks

Contacts can hold separate Reticulum, MeshCore and SIP addresses for a person. neXt links them only when you choose to.

### How to

1. Add a contact in Contacts using the relevant network’s address. MeshCore announces can also supply user contacts.
2. Choose the explicit linking action when you know two identities belong to the same person. A linked person is one contact entry with separate network actions.
3. Use Send MeshCore message or the Reticulum message action deliberately. Telephone shows compatible calling options for known addresses.
4. For SIP, save the person’s extension/server as appropriate for your provider. A Reticulum call ID is not a SIP extension.
5. Use Share My Identity to exchange the selected network’s public identity rather than private keys.

### Keep in mind

- Linking does not bridge messages, transfer keys or make an unreachable address reachable.
- A name seen in a tactical datagram is not automatically a verified MeshCore contact. Save a full public key when needed; the app resolves it from known contacts when possible.

## Discover repeaters, room servers and sensors

Saved nodes are separate from person-to-person contacts. Discovery finds candidate infrastructure; authentication and the node’s firmware decide what you can do.

### How to

1. Open MeshCore Nodes and use Discover new nodes to look for repeaters, room servers and sensors. Allow time for radio responses.
2. Save the intended node and open its page. A route showing 0 outbound and 0 inbound hops means direct radio routing, not successful login.
3. Enter a guest or administrator password only on your device. A verified administrator login exposes the actions supported for that node and firmware.
4. Use Request status or a read-only query before making changes. Password saving is optional and uses the platform’s secure credential support where available.
5. For a room server, log in and use its room conversation. neXt keeps the session unless it discovers disconnection; a reconnect or identity change may require renewed login.

### Keep in mind

- A timeout or “no confirmed server response” means the outcome was not verified. It is not proof that a write failed. Read status/reconnect before repeating a potentially applied change.
- Firmware determines admin actions such as guest access, passwords, time, position, advert intervals and path hashes. Discovery is not permission to administer someone else’s node.
- Room servers are not ordinary hashtag channels or SIP servers.

## Use regions and channel scoping

A region tells compatible repeaters where to forward a scoped channel message. It is separate from the channel name/key and the 1–3 byte path hash size.

### How to

1. After setup, open Tools → MeshCore → Regions. Scan nearby regions or ask a supported repeater, room server or sensor.
2. Use the exact region name agreed by your local group. Names are not limited to three characters; this build validates up to 29 UTF-8 bytes, so emoji can use multiple bytes.
3. Choose a default for channel messages or override an individual channel’s scope. Radio default leaves scope behavior to the existing radio configuration.
4. Leave scoping unchanged if you do not know which region to use. Automatic discovery is optional, off by default, and does not automatically select a new scope.
5. Test scoped text with a peer who shares the channel key and uses compatible regional forwarding.

### Keep in mind

- Scoping applies to channel messages in neXt, not ordinary DMs. It is routing guidance, not access control or encryption.
- A scan timeout does not prove that no regions exist. Firmware support and radio reachability affect discovery.

## Enable optional MediaMesh / Radio2

Radio2 is a second radio profile on one transceiver. The device alternates profiles; it is not two simultaneous physical radios. Standard text works without it.

### How to

1. First verify ordinary MeshCore text. Back up the companion before changing firmware.
2. Choose a compatible companion build for the exact board, radio module and BLE/USB connection from the linked Radio2/Cascade releases. Standard MeshCore firmware is not assumed to support Radio2.
3. In setup or Settings → MeshCore → Radio2, keep an existing profile or explicitly choose the local MediaMesh profile. The US preset is 911.150 MHz, BW250 kHz, SF7, CR4/5; confirm with your group.
4. neXt checks capability and primary-profile preservation, disables cross-profile forwarding and requires media on Radio2. Both peers need compatible media support and matching media parameters.
5. Send a small photo or short recorded clip first. Standard text peers remain useful even if they cannot download media.

### Keep in mind

- MediaMesh media payloads are unencrypted over radio, even when announced in an encrypted DM. Use it only for content you are willing to transmit that way.
- Radio2 does not add live MeshCore phone calls. Use recorded voice clips; live calls belong to LXST or SIP.
- Saved profiles take precedence; do not silently copy primary settings onto the media profile.

## Send photos and recorded voice

neXt supports MediaMesh photos and Codec2 recorded voice in MeshCore DMs and channels, plus tactical attachments. A message announcement and the media download are separate stages.

### How to

1. Connect a compatible Radio2 companion and confirm the recipient has compatible firmware/client support. For channels, share the same channel key and suitable scope.
2. In a MeshCore conversation or channel, choose Photo or Voice clip in the Attachments row. Its editor opens in a scrollable dialog. Record a short clip, stop, preview, then explicitly send. Closing or switching attachment type discards the current draft.
3. On the receiving side, wait for the indicated parts to download. Play/view only after completion; an announcement arriving does not mean all media parts arrived.
4. If interrupted, reconnect and use the explicit retry/download control on the same item. Completed cached media remains usable offline; incomplete downloads are not presented as complete.
5. If the sender cannot be resolved, add/verify their full MeshCore public key. Do not substitute a short displayed name for a cryptographic identity.

### Keep in mind

- Small images and short audio are best on a shared low-bandwidth mesh. Avoid repeated automatic resends.
- Codec2 1200 voice and standard photos were tested both ways with MeshCore Open TAK/VOX. Other codecs, firmware revisions or client-specific formats are not automatically covered.
- Media bytes are unencrypted over RF. A private channel or encrypted DM announcement does not change this limitation.

## TAC: team maps, points and drawings

TAC brings shared situational information to the map: team positions, pins, routes, shapes, reports and attachments over MeshCore. It is not emergency dispatch or automatic tracking.

### How to

1. Open Map and the MeshCore team tools. Select a private team channel, share its key with the intended team, and confirm a usable scope.
2. Set a team alias and review what you will share. A private team key is membership material; an alias is not independently verified identity.
3. Create a pin, drawing or route locally. Review its coordinates, fitted wire size and selected channel before explicitly sharing.
4. Inspect received items, stale-position labels, map-centre distance and true bearing. A one-time GPS range reference is local unless you separately choose to share a position.
5. Enable team alerts or geofence monitoring only if desired. Review alert settings separately from ordinary channel chat notification modes.

### Keep in mind

- Delayed, missing or spoofed updates are possible. A map is not guaranteed to show everyone’s current location.
- Geofence crossing alerts compare received observations; they cannot guarantee a real-time crossing or detect every unobserved pass-through.
- CASEVAC/nine-line reports are structured team messages, not a connection to emergency services or medical advice.

## Prepare maps for online and offline use

A map can show overlays while its background is blank. Map tiles are the background images; they must be available locally for offline use. Wi-Fi being enabled does not prove the map has a network route or downloaded coverage.

### How to

1. Before going offline, open Map with internet access and inspect the area and zoom levels you need.
2. The bundled map includes a world overview and a compact PNW/southern British Columbia overview through zoom 9. Open Map, tap Offline maps, then choose Download and use regional detail (104 MB) for road/town context through zoom 12. The app verifies and selects the download automatically. You can also restore the included overview or import your own MBTiles file from the same panel. Coverage is limited; it is not every place at every zoom.
3. Confirm that the map source and selected MBTiles file match the view. A tile set’s area and zoom range determine what can display.
4. Test with network access unavailable before leaving. Pan and zoom through the intended operational area rather than checking a single screen.
5. If one phone works and another does not, compare their downloaded files, selected source, coverage and zoom. Each installation has its own tile storage.

### Keep in mind

- Opening an area online or having tiles on another device does not guarantee offline coverage on this device.
- Position overlays can still exist over a blank background. Missing tiles do not necessarily indicate a radio problem.
- Import maps from sources you are entitled to use; background-map coverage and freshness vary.

## Share location only when you choose

Reading your phone’s position and transmitting it to a team are different actions. neXt keeps automatic team sharing off until you explicitly start it.

### How to

1. Select the intended private team channel and review the alias, scope and recipients before starting sharing.
2. On Android grant the requested location/notification permissions, choose an interval and optional stop duration, and confirm. A foreground location service keeps the timed session visible.
3. Use Stop sharing in the app or service notification to revoke the session. Changing identity/channel, disconnecting or restarting can end sharing; it is not a silent boot-time tracker.
4. Check the submission count and last-submission age. Submission is not proof that every teammate received the point.
5. For local range/bearing only, use the one-time GPS reference instead of automatic sharing. It expires and does not itself send radio traffic.

### Keep in mind

- Location reveals where you are. Share only with the intended team and check device permission/background restrictions.
- A 15-minute screen-off field check received 12 updates with no displayed percentage drop on the test phone. That short stationary check is not a battery-life guarantee.
- Received team positions can be stale or inaccurate; the app’s labels and reported accuracy should inform how you use them.

## Interoperate with Open TAK, ATAK and TAK servers

neXt implements selected compatible tactical formats. It is not a complete replacement for ATAK or a promise to handle every third-party plugin, datatype or server.

### How to

1. For MeshCore Open TAK/VOX peers, use compatible private team/channel configuration and firmware. Begin with text or a simple pin, then test the specific drawing/report/media type you need.
2. For local file interchange, preview a CoT file or TAK mission package. Review its entries before importing/sharing. Incoming file content is not automatically broadcast to the radio.
3. Export selected supported points, drawings/routes and optional cached media. Exports do not include channel keys. Large geometry may need simplification to fit MeshCore radio limits.
4. For a TAK server, explicitly configure and connect the supported TLS session, CA/client certificate requirements and negotiated protocol. Certificates and session credentials are kept for the current session; enrollment is separate.
5. Review received server items locally. Sending an item to a server or sharing it onto MeshCore requires its own deliberate action. Disconnect when finished.

### Keep in mind

- Live Open TAK checks covered neXt routes/CASEVAC in the documented direction and media in both directions. Reverse-authored tactical items are not all equally tested.
- Official ATAK CIV recognized a synthetic neXt package with seven map entries and two media files. That proves that fixture’s import, not exhaustive ATAK compatibility.
- Server protocol, certificate and package paths were tested with a controlled local server. Independent deployments still need their own checks.

## Set up SIP / HOIP extension calling

SIP provides provider-based extension calls over an IP connection. It uses its own account and audio path, independently of Reticulum and MeshCore.

### How to

1. Enable SIP in App features, then Settings → SIP → Add account. Enter your own extension and password; no test account is shipped.
2. Confirm the provider server, port and transport. The editable HOIP preset is premium.hamsoverip.com:5160 using UDP. Use your account’s assigned details if they differ.
3. Leave Save password securely enabled if desired. Android uses Keystore-backed storage and excludes saved SIP credentials from backups. Without saving, re-enter the password after the service stops.
4. Allow Wi-Fi and/or mobile data independently. I2P is shown only when a supported transport exists and needs a reachable compatible endpoint; an ordinary public server is not automatically available over I2P.
5. Select the account, connect and enable automatic reconnection if you want persistent service. Open Telephone to call an extension or use a SIP contact.

### Keep in mind

- HOIP calls other extensions; it does not provide ordinary mobile/PSTN calling here. There is no need to replace your Android carrier dialer.
- Provider connection limits can cause rejection when stale registrations fill the allowed slots. Avoid repeatedly toggling or adding duplicate accounts while diagnosing.
- Registration success is necessary but not sufficient: test an incoming background call and two-way speech.

## Make, receive and keep SIP calls reachable

Telephone contains the SIP dialer and connection status. Account credentials are managed under Settings → SIP, leaving the calling screen simpler.

### How to

1. Check the selected SIP account is registered. Use Reconnect when the status shows it is disconnected.
2. Dial an extension supported by your provider. On another client such as Linphone, use an appropriate account/server and test two-way audio.
3. For incoming calls, use neXt’s Answer/Decline screen or notification. Allow Android call notifications and background execution. On Android 14 or later, use Allow lock-screen call display if SIP settings requests it; this lets incoming calls appear above the lock screen.
4. Enable automatic reconnection for launch/recovery. Permit both Wi-Fi and mobile data if you want failover; switching routes can still end an active call.
5. If registration returns 401 or 403, verify the actual server, UDP/TLS transport, extension and provider connection limit. The provider’s console and account details matter.

### Keep in mind

- A normal SIP digest challenge can use 401 before successful authentication. A final unauthorized state is not the same as a harmless challenge.
- 403 means the server refused the request; a full registration quota is one possible cause, not the only explanation.
- Keep microphone access enabled and use headphones for testing. Clear two-way speech has been verified against Linphone in the local test setup; real networks can differ.

## Import, export and migrate safely

A backup is only as complete as the data it contains and the fields this app can restore. Always preview the proposed changes and keep the original file.

### How to

1. For Reticulum, supported raw-key/Base32 imports restore your identity. They do not claim to restore another application’s entire contacts/history/configuration database.
2. For MeshCore, choose a recognized official-client JSON configuration or supported encrypted identity backup. If a supported multi-device file is detected, choose the intended device.
3. Connect the intended companion, preview the file, select the supported sections and apply explicitly. Review identity-replacement confirmation separately from contacts/channels.
4. If a file has only a public key, it cannot restore the private radio identity. Unsupported fields are shown rather than silently claimed as imported.
5. Export and safely store your own backup before firmware changes. Keep backup passwords separately and test that you can open the file before relying on it.

### Keep in mind

- Device metadata can prefill a Bluetooth address, but Android Bluetooth bonds/permissions still need system pairing.
- Saved SIP/node credentials and TAK session certificates are not assumed transferable. Re-enter credentials when required.
- An uncertain import receipt should be checked before retrying a write. Selecting no applicable new sections can legitimately produce no additions; it is not a promise that every backup field exists.

## Explore the other tools without mixing services

The Tools area groups different capabilities. Choose the network/tool deliberately; not every tool speaks every protocol.

### How to

1. Use MeshCore tools for trace path, RX log, regions and noise floor where supported. Diagnostic traffic still depends on firmware and a reachable node.
2. Use Reticulum propagation tools for LXMF store-and-forward; paper messages for QR/URI handoff; and path/interface tools for Reticulum connectivity.
3. Use Nomad Network for compatible pages/files reachable over Reticulum. It is not the normal public web browser and does not fetch MeshCore channels.
4. Use Relay Chat for Reticulum relay hubs/rooms. The neXt support server is an RRC relay, not a MeshCore room server.
5. Advanced tools such as remote shell, file transfer, forwarding, plugins and repository services require their own endpoints, permissions and configuration. Enable only what you intend to use.

### Keep in mind

- Tool availability varies by build/platform and selected features. A hidden menu does not prove an underlying service has stopped.
- Translation is local UI/content assistance where configured; it does not translate protocols or make incompatible apps communicate.

## Who can I communicate with?

Compatibility follows the protocol and content format—not the fact that two apps both use LoRa, maps or a similar display name.

### How to

1. Reticulum text: use an LXMF-compatible peer such as Sideband or NomadNet with a reachable destination. Test text first; rich content can differ.
2. Reticulum calls: both ends need compatible LXST telephone support. LXMF-only peers are not automatically callable.
3. MeshCore text: other MeshCore clients can communicate through compatible companions on the same primary radio profile and appropriate contact/channel configuration. Meshtastic is a different protocol.
4. MeshCore media: neXt and MeshCore Open TAK/VOX have passed Codec2 1200 voice and standard-photo tests both ways. Firmware/profile/media-format agreement is required; not every MeshCore app supports media.
5. Tactical interchange: selected Open TAK formats and CoT/mission packages are supported with the limits described in the TAK article. SIP: provider-compatible clients such as Linphone can call extensions reachable through that provider.

### Keep in mind

- There is no automatic Reticulum ↔ MeshCore ↔ SIP gateway. Contact linking is an address-book convenience.
- A phone’s Bluetooth link to its companion is not the over-the-air mesh protocol. Swapping phone apps and reflashing radio firmware are different actions.
- Do not assume an app’s newest feature is supported here. Check the neXt release notes, exact firmware and the tested feature rather than a broad “compatible” badge.

## Privacy, permissions and what leaves the device

Different services have different privacy properties. Check what is being sent, on which network, to whom, and whether it is encrypted.

### How to

1. Protect private identity exports, backup passwords, SIP credentials and private channel keys. Review logs/screenshots before sharing them for support.
2. Reticulum traffic uses its own cryptographic identities. Do not assume that copying a name or linking a contact verifies the other network’s identity.
3. MediaMesh audio/images are unencrypted over radio. The DM announcement may be encrypted while the media is not.
4. Automatic GPS sharing, team alerts, server connections, package uploads and radio sharing require explicit actions. Stop sharing/disconnect when finished.
5. Grant Bluetooth/USB, microphone, notifications and location permissions only for the features you use. App visibility settings are separate from Android permissions and service controls.

### Keep in mind

- Private channels are shared-key groups, not a replacement for verifying individual identities. Received tactical datagrams can be stale or spoofed.
- SIP transport/security depends on the provider configuration. The UDP HOIP preset is not a claim of end-to-end encrypted calling.
- This guide is a local document: its checklists store only progress in this browser. It does not collect keys, send messages, configure radios or enable location.

## Your first successful test

Verify one small action on one service before combining radios, media or advanced tools.

### How to

1. Choose a known peer and network. Agree on which client each person is using and which address/channel/profile applies.
2. Send one short text. Ask the peer to reply, then confirm both directions. Use a private test channel for repeated MeshCore tests.
3. Inspect network labels, DM acknowledgments and connection status. Do not mistake heard repeats or a local send entry for recipient confirmation.
4. For calls, separate the phones and test speech in both directions. For media, wait for all parts and play/view the received content.
5. Once the basic path works, add one feature at a time: second radio, mentions-only alerts, media, maps or a provider call.

### Keep in mind

- Avoid flooding a public channel with repeated tests. Radio airtime is shared.
- Record what worked: app version, radio model/firmware, profile, peer app and test type. These details are more useful than “it doesn’t work.”

## Troubleshoot by layer

Start with the failing layer. A map-tile problem, Bluetooth connection problem, radio-profile mismatch and SIP registration error need different fixes.

### How to

1. App: is the feature visible/enabled? If a menu is hidden, check App features. Reopen first launch with Run setup guide.
2. Device link: paired is not connected. For BLE, close competing apps and verify the selected companion/RNode. For USB, check OTG/data/power, permissions and re-enumeration.
3. Network: compare primary radio parameters, channel key/scope and peer reachability. Check Reticulum interfaces or the SIP provider route as appropriate.
4. Service: discovery is not login; registration is not two-way audio; announcement receipt is not completed media. Read the actual state/error.
5. Content/UI: incomplete media needs an explicit retry; blank offline maps need local coverage; missing alerts need notification/mute/DND checks. After an unconfirmed node write, verify before repeating it.

### Keep in mind

- Use the matching network support channel and include reproducible steps. Do not repeatedly replay unknown writes or fill the mesh with test traffic.
- An error that disappears after reconnection may be a session/transport problem, not proof that the command was invalid.

## Get help, suggest a feature or join the conversation

Meshchat neXt Relay hosts bug reports, feature requests and general discussion over Reticulum. GitHub reporting is also available through the Meshchat neXt issue tracker linked in About → Contact / Support.

### How to

1. Connect Reticulum through a usable interface. Open About → Contact & support, then choose Bug reports, Feature requests & suggestions, or General chat.
2. The relay destination is ef933cd2c155bbef703fdf59100598a8. Exact room names are “bug reports”, “feature requests & suggestions” and “general”.
3. For a bug, include neXt version/build, platform, service, radio model/firmware if relevant, what you expected, what happened and the shortest reproduction steps.
4. For a feature request, explain the task you want to accomplish and the current obstacle. Distinguish a neXt change from a request for external firmware/provider behavior.
5. Review logs/photos for private keys, credentials, private messages and coordinates before posting. Opening a support room does not submit a report automatically.

### Keep in mind

- The official repository is github.com/hk1200/Meshchat-neXt. Use its Releases page for official downloads and its Issues page for GitHub reports.
- The support relay is Reticulum RRC. It is not a MeshCore hashtag channel, room server or SIP endpoint.
- For support and chat amongst local MeshCore users, add #meshchat_next as a public hashtag channel. Its reach depends on your local mesh. It is not monitored by the developer; use GitHub or Meshchat neXt Relay for developer reports and feature requests.

## FAQ / How do I?

### Do I need all three services?

No. Choose any combination in Settings → App features. Their visibility and connections are independent.

### Can I use neXt without a radio?

Yes: Reticulum over TCP/LAN and SIP over a suitable IP connection need no LoRa radio. MeshCore radio messaging needs a companion.

### Does one message go to both meshes?

No. Choose the network for the message. neXt does not automatically bridge Reticulum and MeshCore.

### Can an RNode and MeshCore run together?

Yes, as independent connections to separate compatible devices. They keep their own radio settings and identities.

### Can the same board be an RNode and a MeshCore companion?

Its installed firmware determines its role. Do not assume one physical transceiver can run both companion protocols at once.

### Where did my setup go?

Use Settings → App features → Run setup guide. Non-secret draft choices can resume; private backup files/passwords must be supplied again as needed.

### Does disabling a feature stop its service?

The App features switches control visible functions. Use the service’s own disable/disconnect control to stop its connection.

### Why is my paired radio not connected?

Pairing is the system bond. You must select/connect the right device in neXt. Close another app controlling the same companion.

### Why does USB need refreshing after reconnect?

Android can assign a new USB device instance after unplugging. Refresh, select and grant permission again if needed; check the OTG cable and power.

### Are the default frequencies right for everyone?

No. They are starting presets. Confirm region, local group, firmware and hardware constraints; saved values take priority.

### Does Radio2 need the same settings as the main mesh?

No general rule says so. Use the primary profile for your mesh and the agreed media profile for Radio2. Compatible endpoints need to agree on each respective profile.

### Can I use normal MeshCore firmware?

Yes for ordinary text and supported tools. Radio2 media needs compatible firmware on the relevant nodes/clients.

### Can I make a live MeshCore phone call?

This build offers recorded MeshCore voice clips. Live telephone calls use Reticulum LXST or SIP, not Radio2.

### Are MediaMesh photos and voice private?

The media bytes are unencrypted over RF, even if their DM announcement is encrypted. Do not transmit sensitive media on that assumption.

### Why is a channel message not marked delivered?

Channels do not have per-recipient delivery receipts here. Radio acceptance and heard repeats are not proof that every recipient received it.

### Do repeats tell me how many repeaters heard me?

No. The count is observed matching retransmissions, not distinct repeaters or recipient acknowledgments.

### Does a ban remove someone from the channel?

It hides that sender locally in neXt. It does not remove them from the mesh or suppress messages in other clients.

### How do I unhide Public or another channel?

Open Manage channels and show hidden channels, then unhide it. Hiding and deleting are different actions.

### Do hashtag capitals matter?

New public names are normalized to lowercase. Existing mixed-case channels keep their key; peers need that exact key or a deliberately recreated lowercase channel.

### How do I notify only the person I reply to?

Use Reply to insert the person’s mention. Their own channel notification setting decides whether they receive an alert.

### Are regions limited to three characters?

No. The separate path hash uses 1–3 bytes. Region names use a UTF-8 byte limit; this build accepts up to 29 bytes.

### Do DMs need a region scope?

Ordinary DMs keep their routing. The region selection described here applies to channel messages.

### Why does 0 outbound / 0 inbound not mean logged in?

Those are route hop counts: zero means direct. Login is a separate authenticated exchange.

### A node command timed out. Should I send it again?

First read status or reconnect and verify. The write may have applied even though its reply was not confirmed.

### Can I import my entire other app?

Only supported backup formats/fields are restored. A public key cannot restore a private identity, and Bluetooth pairing cannot be imported as an Android bond.

### Why can’t I see offline map tiles on a new phone?

That phone needs its own usable tile file/cache for the area and zoom. Another phone’s map data and enabled Wi-Fi do not provide offline coverage.

### Does opening Map send my location?

No. Local viewing, a one-time range fix and explicit team position sharing are separate actions. Sharing must be started deliberately.

### Can tactical positions be treated as live and verified?

No. They may be delayed, missing, stale or spoofed. Consider age and accuracy; an alias alone does not prove identity.

### Can I talk to Meshtastic users?

Not directly through MeshCore or Reticulum just because both use LoRa. It is a different protocol; no automatic bridge is supplied.

### Can I talk to Sideband or NomadNet?

Compatible LXMF text can work over a reachable Reticulum path. Rich attachments and live calls depend on the other app’s support.

### Can I exchange voice with Open TAK/VOX?

Codec2 1200 clips were tested in both directions with compatible Radio2 firmware/profiles. That is not a guarantee for every codec or app version.

### Does neXt replace ATAK?

No. It implements selected tactical and interchange features, with documented format/server limits. Test your specific workflow.

### Does HOIP call ordinary phone numbers?

Not through this extension-calling setup. Use a provider-supported extension; it is separate from the phone’s carrier dialer.

### Why can SIP register but not ring?

Background restrictions, notifications, route/NAT/provider reachability or account selection can differ from registration. Test an actual incoming background call.

### What does SIP 403 mean?

The server refused the request. Credentials, policy or registration limits can cause it. Check the provider rather than assuming a single cause.

### Can SIP fall back from Wi-Fi to mobile data?

Allow both networks. It reconnects using an available permitted route; an active call can still end during handover.

### Why is I2P not listed?

The option appears only when supported connectivity is available. A normal public SIP server does not become an I2P endpoint by checking a box.

### Will this guide change my settings?

No. It is a local reading aid. Checklists save browser progress only; no keys, radio configuration, calls or GPS are requested.

## Glossary

- **Announce:** A discovery advertisement for a network identity or service; not a chat message.

- **Aspect:** A Reticulum service label, such as LXMF delivery or LXST telephony.

- **Bandwidth (BW):** Width of the radio channel, normally shown in kHz.

- **BLE:** Bluetooth Low Energy: one way a phone connects locally to a supported radio.

- **Channel:** A shared MeshCore conversation using a name-derived or shared key.

- **CoT:** Cursor on Target: tactical event formats used in TAK interchange.

- **Companion:** A MeshCore client radio controlled by an app.

- **CR:** Coding rate: an error-correction radio setting.

- **DM:** Direct message to one network identity.

- **Hash / public address:** A network identifier. It is not a private-key backup.

- **Interface:** A connection that carries Reticulum traffic, such as RNode, LAN or TCP.

- **LXMF:** The messaging format used by compatible Reticulum messaging apps.

- **LXST:** The stream/telephone system used for neXt’s Reticulum live calls.

- **MediaMesh:** The compatible media-transfer workflow used for MeshCore photos and recorded voice.

- **OTG:** Android USB host connection, normally using an adapter or hub.

- **Path hash:** A shortened identifier for repeater hops, selectable at 1–3 bytes on supported firmware.

- **Propagation node:** A Reticulum/LXMF store-and-forward helper for offline delivery.

- **Radio2:** An alternate profile on one supported transceiver, not a second physical radio.

- **Region / scope:** MeshCore channel forwarding guidance, separate from the channel key.

- **RNode:** A radio modem/interface used by Reticulum.

- **Room server:** A MeshCore node providing a hosted room/session.

- **RRC / Relay Chat:** Reticulum relay hubs and rooms, separate from MeshCore room servers.

- **SF:** Spreading factor: a LoRa radio setting affecting transmission behavior.

- **SIP:** The provider-based calling protocol used for extension calls.

- **TAK / TAC:** Tactical map/data tools. neXt supports selected workflows and formats.

- **TCP:** An IP connection type used to reach a Reticulum entry point.

- **TX power:** Transmit power, shown in dBm. Device/region limits apply.

## Sources and compatibility references

- [Reticulum manual](https://reticulum.network/manual/)

- [LXMF reference implementation](https://github.com/markqvist/LXMF)

- [MeshCore project and companion firmware](https://github.com/meshcore-dev/MeshCore)

- [MeshCore firmware releases](https://github.com/meshcore-dev/MeshCore/releases)

- [Radio2 / Cascade firmware releases](https://github.com/mikecarper/MeshCore/releases)

- [Open TAK MediaMesh guide](https://github.com/jade-on-mesh/meshcore-open-tak/blob/main/documentation/media-mesh.md)

- [RMAP entry-point information](https://rmap.world/services.html)

- [Hams Over IP](https://hamsoverip.com/)

- [ATAK CIV source / format reference](https://github.com/deptofdefense/AndroidTacticalAssaultKit-CIV)

## Review boundaries

This guide describes Meshchat neXt 0.1.2. Compatibility is specific to the firmware, codec, server and package in use; it does not imply support for every ATAK deployment. A firmware assistant is not included. External projects and firmware change. Check the exact neXt release notes and hardware before flashing.
