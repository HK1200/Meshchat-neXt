// SPDX-License-Identifier: 0BSD
export const SETUP_HELP = {
    networks: [
        [
            "Reticulum",
            "Messages and calls over a network that can use radio, local Wi-Fi/Ethernet or internet interfaces. No MeshCore radio or SIP account is required. Selecting it shows Reticulum menus and setup steps; a connection is configured on the later connection page.",
        ],
        [
            "MeshCore",
            "Text DMs, channels and node tools through a separate MeshCore companion/client radio. An RNode is not a MeshCore companion. Selecting it shows MeshCore menus; it does not connect or reflash a device. Radio2 media is optional.",
        ],
        [
            "SIP",
            "Internet extension calls using an account from a SIP provider such as HOIP. It is independent of both radio networks. Selecting it reveals SIP setup; it does not create an account. HOIP extension calling is not ordinary mobile/PSTN calling.",
        ],
        [
            "Existing installation and storage",
            "Import only your own backups. Reticulum raw private keys restore an identity, not every app setting. MeshCore import previews supported fields before applying them. Android Bluetooth pairing remains a system step. Storage controls appear only when the device offers a storage choice; app-specific external storage is not a shared public backup.",
        ],
    ],
    identity: [
        [
            "Display name",
            "The readable name others see in your Reticulum announces. It can change without changing your private key or destination addresses. It is not a unique username or proof of identity.",
        ],
        [
            "Use this device’s identity",
            "Keep the Reticulum identity neXt already has. New installations create an identity locally; there is no central Reticulum registration or password to obtain.",
        ],
        [
            "Import an identity key file",
            "Use a raw private identity file exported from your Reticulum installation. A public address, QR contact card or arbitrary backup ZIP cannot substitute for it. Your current identity is retained separately; an app restart may be required.",
        ],
        [
            "Import a Base32 identity",
            "Paste your own private identity export only when it is in the supported Base32 format. This restores the matching identity; it does not merge chat histories. Never paste a private key into a support report.",
        ],
    ],
    reticulum: [
        [
            "Internet · TCP",
            "Adds or reuses a Reticulum connection to rmap.world:4242 when you continue. It uses the phone/computer’s internet connection and needs no RNode. It provides a path into Reticulum, not a MeshCore gateway. Existing connections are kept.",
        ],
        [
            "Server host and port",
            "The host identifies a Reticulum entry point; the port identifies its listener. The preferred preset is editable. Use a Reticulum server, not a SIP server or web-page URL. Your network must permit the connection.",
        ],
        [
            "Nearby devices on the same network",
            "Adds automatic Reticulum discovery on your local Wi-Fi or Ethernet network when needed. It does not require internet, but both devices need local network access; guest Wi-Fi isolation can prevent discovery. This is not Bluetooth discovery.",
        ],
        [
            "Connect an RNode · Bluetooth LE or Classic",
            "An RNode carries Reticulum packets over radio. Pair it in the system first, then choose the transport its firmware supports. Bluetooth LE is the new-setup default; Classic is for devices that need it. The paired list can also contain non-RNode devices: choose your actual RNode.",
        ],
        [
            "Connect an RNode · USB / serial or over IP",
            "USB needs a data cable, and Android normally needs OTG and USB permission. RNode over IP needs the address of a reachable RNode TCP endpoint. Neither option turns a MeshCore companion into an RNode. Add RNode connection explicitly saves this interface.",
        ],
        [
            "RNode frequency, bandwidth, SF, CR and power",
            "These describe how your radio transmits. Nearby peers must use compatible radio parameters. New-form values are 914.875 MHz, 125 kHz, SF8, CR4/7 and 17 dBm; these are starting values, not a worldwide standard. Confirm your local group and hardware limits before adding it. Existing interfaces are not overwritten.",
        ],
        [
            "Receive announces",
            "Announces advertise reachable users and services. Setup permits ordinary announces from enabled outbound TCP interfaces instead of treating them only as bootstrap links. It keeps private interface boundaries. Hearing an announce does not automatically save a contact or prove end-to-end delivery.",
        ],
    ],
    meshcore: [
        [
            "Keep what is already on my client",
            "Use the companion radio’s existing identity, contacts and channels. Connecting reads them; it does not replace its primary radio settings with a default preset. Close other apps using that same companion first.",
        ],
        [
            "Import a MeshCore backup",
            "Choose a recognized JSON configuration or supported encrypted identity backup, connect the intended companion, preview and select the sections, then explicitly import. Supported fields vary by file and firmware. Paired-device metadata may suggest a connection, but cannot create Android Bluetooth bonds. Private identity replacement needs an additional confirmation.",
        ],
        [
            "Bluetooth client connection",
            "Pair a MeshCore companion in Android Bluetooth settings, refresh the list, select the companion, and connect. Your RNode uses a separate connection. One companion generally should not be controlled by two apps at the same time.",
        ],
        [
            "USB client connection",
            "Attach a USB-companion firmware device with a data-capable OTG connection. Refresh USB radios, select it, allow Android access, and connect. After unplugging or USB re-enumeration, refresh/select/connect may be necessary. Bluetooth-only firmware is not guaranteed to offer USB client transport.",
        ],
        [
            "Primary radio profile and client name",
            "Read the profile first. Frequency, bandwidth, spreading factor and coding rate must match your local MeshCore group; power is limited by the device and local rules. Path hashes use 1–3 bytes on supported firmware. Naming the client changes its readable name, not its public key.",
        ],
    ],
    radio2: [
        [
            "Keep my current setup / decide later",
            "Leaves Radio2 unchanged and does not probe or apply a new profile. Choose this if you are unsure or are importing a working setup. Text messaging does not require Radio2.",
        ],
        [
            "Standard MeshCore messaging · Radio2 off",
            "Uses ordinary MeshCore messaging. neXt checks the firmware and turns Radio2 off if it is supported and enabled. Firmware without Radio2 remains usable for text; MediaMesh photo and recorded audio transfers will be unavailable.",
        ],
        [
            "Radio2-compatible firmware · enable media",
            "Requires an appropriate companion build for the exact board/module and connection type. neXt checks capability before enabling it. Both endpoints need compatible media support. This uses another profile on one transceiver, not simultaneous second-radio hardware or live phone calling.",
        ],
        [
            "Keep the saved Radio2 profile",
            "Preserves the media settings already saved on the radio. If no usable profile exists, setup asks for a valid choice instead of silently substituting a regional preset.",
        ],
        [
            "US MediaMesh preset",
            "Explicitly selects 911.150 MHz, BW250 kHz, SF7 and CR4/5. Confirm that your group uses it and that it is appropriate locally. The primary mesh can use different settings. neXt keeps primary settings, disables crossing and requires media on Radio2. Media payloads are unencrypted over radio even when announced in an encrypted DM.",
        ],
    ],
    sip: [
        [
            "Add account and selected account",
            "Enter your own provider extension and password. A label helps distinguish accounts; it is not a login. Add more accounts if needed and select which one is active. No test user credentials ship with neXt.",
        ],
        [
            "Enable SIP · reconnect automatically",
            "Keeps the selected account connected while enabled and reconnects on launch or network loss. Background ringing also depends on Android notifications and background execution permissions. It does not enable Reticulum telephone or MeshCore voice.",
        ],
        [
            "Server, port and transport",
            "The editable HOIP preset is premium.hamsoverip.com, port 5160, UDP. Use the server/port assigned by your provider. Other providers may need different values. SIP registration alone does not prove two-way audio or incoming-call reachability.",
        ],
        [
            "Save password securely",
            "Enabled by default. On Android, saved SIP passwords use Keystore-backed encryption and are excluded from backups. With saving off, supply the password again after the service stops. Removing an account removes its stored credentials.",
        ],
        [
            "Allowed networks · Wi-Fi, mobile data and I2P",
            "These are independent permissions. SIP can use any selected available network, preferring Wi-Fi. Allow mobile data for failover; a handover may end an active call. I2P appears only when a supported usable transport exists and needs an appropriate reachable SIP endpoint. It does not make a normal public HOIP server an I2P service.",
        ],
        [
            "Connect, disconnect and edit",
            "Connect registers the selected account. Disconnect ends its registration/service connection. Editing changes the selected account; provider connection limits can affect repeated registrations. Telephone shows calling controls and connection status; account configuration stays under Settings → SIP.",
        ],
    ],
    ready: [
        [
            "Start using neXt",
            "Finishes first-launch setup and opens an enabled communications area. It does not automatically publish your position, send an announce, place a call or join a public chat.",
        ],
        [
            "Revisit or change the setup",
            "Use Settings → App features → Run setup guide to reopen it. Feature switches control what you see; use each service’s own disconnect/disable controls to stop its connection. Network identities and existing data remain separate.",
        ],
    ],
};
