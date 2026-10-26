# MeshCore in Meshchat neXt

MeshCore and Reticulum use separate radio connections, identities, and message transports. A MeshCore companion and an RNode can operate at the same time. Network labels identify which system a conversation or action uses.

## Connect a radio

On Android, open **Settings → MeshCore**. For Bluetooth, pair the companion in Android settings, refresh paired radios, and select it from the list. Choose the MeshCore companion rather than your RNode. For USB, attach a supported companion through OTG, refresh USB radios, select the device, and allow Android USB access.

Read settings from the radio before making changes. Saved values take precedence. When no values have been set, the primary preset is 910.525 MHz, 62.5 kHz bandwidth, SF7, CR4/8, 22 dBm, and one-byte path hashes. The radio checks supported values; its power limit can be lower. Path hash size is selectable from one to three bytes on supported firmware.

USB two-way messaging has been tested. Automatic recovery after USB device re-enumeration remains incomplete; refreshing, selecting, and reconnecting may be necessary. A stable OTG cable and power arrangement matter.

## Identity and contacts

The companion owns its MeshCore identity. Its display name and public address appear in MeshCore settings. That identity is separate from the app's Reticulum identity.

MeshCore users appear in the existing Contacts area. Linking a MeshCore contact to a Reticulum contact is an explicit choice: names alone never merge identities. A linked person occupies one contact entry and retains separate messaging actions and addresses for each network. Linking does not bridge messages between networks.

**Share My Identity** can share the selected network identity. Encrypted identity backups contain the private MeshCore identity; keep the backup and its password securely. Configuration import supports recognized official-client backup fields where supported, with a review of the proposed changes. Unsupported data is not silently presented as restored. Legacy authenticated identity backups remain importable.

## Direct messages and announces

MeshCore direct messages appear in Conversations with a MeshCore label. Reticulum conversations remain separate. Direct messages retain delivery acknowledgments; heard-repeat counts are a separate measurement.

Under Announces, select Reticulum or MeshCore for independent lists. A repeated announce updates the existing device entry rather than adding another row.

## Channels, replies, and notifications

Expand **MeshCore Channels** in the sidebar. Each channel shows its unread count; the parent summarizes unread messages. Manage channels to add public hashtag or private-key channels and reorder them with the arrow controls.

Channel notifications offer all messages, mentions only, or muted. Mentions only alerts for the radio's display name in `@[Display name]` form, including its spaces and emoji. Replies insert the selected sender's mention. Muted channels suppress message alerts, including mentions; their messages remain visible and count as unread.

Opening a channel or tapping its notification targets the first unread message when available. Notification labels identify MeshCore. Channel banishment hides the selected sender's messages locally and appears in Banishment; it does not remove a sender from the mesh or alter other clients.

Outgoing channel messages show radio acceptance, not recipient delivery receipts. Both channels and DMs can show heard repeats when packet tracking is available. A repeat count measures observed retransmissions; it does not count unique repeaters or prove delivery. Packets missed during disconnection cannot be reconstructed.

## Repeaters and room servers

Use **MeshCore Nodes** to save and open advertised repeaters and room servers. Login and response verification are separate from route discovery. Zero outbound and inbound hops means a direct route; it does not mean login succeeded.

Enter passwords on the device. A verified administrator login exposes the supported management actions; ordinary room access provides room messaging. After an unconfirmed response, read the displayed recovery guidance rather than repeatedly replaying a write. Radio firmware and permissions determine the available actions.

## Optional Radio2 / MediaMesh profile

Expand **Radio2 · MediaMesh** only when using compatible firmware. Read its existing configuration first. Enabling an unset profile offers the MediaMesh preset: 911.150 MHz, 250 kHz bandwidth, SF7, CR4/5, receive/transmit, and automatic preamble. Existing saved values are loaded instead of overwritten by defaults.

One transceiver alternates between profiles; Radio2 is not a second physical transmitter. Power is shared with the primary profile. Applying the preset disables cross-profile forwarding and requires media to use Radio2. Primary radio settings are checked for unintended changes.

Compatible firmware enables MediaMesh photos and recorded voice clips in MeshCore DMs, channels and tactical attachments. See the interactive guide for setup, interoperability and the important unencrypted-radio-media limitation.
