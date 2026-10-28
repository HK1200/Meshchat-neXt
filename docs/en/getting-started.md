# Getting started with Meshchat neXt

Meshchat neXt is a local-first mesh communications client for Reticulum and MeshCore. It combines direct messaging over LXMF, voice calls over LXST, NomadNet page browsing, relay chat, maps, and a large set of Reticulum utilities in one application you can run on a desktop, a headless server, or a mobile device.

Official Android and Linux downloads are available from [Meshchat neXt Releases](https://github.com/HK1200/Meshchat-neXt/releases). Official builds use signed update feeds. Community support is available through Meshchat neXt Relay and GitHub Issues; see the README and release notes for platform requirements and known limits.

For an Android MeshCore companion, open **Settings → MeshCore**. Its USB/Bluetooth connection is independent of the RNode configured under **Interfaces**. See [MeshCore](meshcore.md) for contacts, channels, notifications, backups, and Radio2.

## What you need to know first

Reticulum is the mesh networking layer. It handles identities, paths, interfaces, and encrypted transport between nodes. LXMF is the messaging protocol Meshchat neXt uses for conversations, attachments, and propagation. LXST is the telephony layer used for audio calls.

Meshchat neXt does not replace Reticulum. It runs Reticulum inside a Python process, exposes a web UI, and stores your per-identity data locally in SQLite.

## How the application is laid out

When you open Meshchat neXt you work inside a single-page web interface. The sidebar lists the main areas of the app. The **Tools** page groups diagnostics and utilities. **Settings** holds per-identity configuration. **Identities** lets you create or switch between separate cryptographic identities.

Typical first-day workflow:

1. Install Meshchat neXt using a method that fits your device. See **Installation and setup**.
2. Open the web UI. The default address is https://127.0.0.1:8000 when HTTPS is enabled.
3. Go to **Interfaces** and add a way to reach the mesh. A TCP client, community interface suggestion, or LoRa RNode are common starting points.
4. Wait for paths and announces to populate. Peers appear in the announces list and in feature-specific views.
5. Open **Messages** to start an LXMF conversation, or **Nomad Network** to browse a page node.

## Runtime shape

Meshchat neXt ships as one Python service that serves both the API and the built frontend assets.

```
Browser or Electron window
    |
    v
Vue 3 frontend (hash routes such as #/messages)
    |
    |  REST under /api/v1/*  and  WebSocket at /ws
    v
meshchatnext/meshchat.py (aiohttp server)
    |
    +--> SQLite database (per identity)
    +--> LXMF router and message store
    +--> LXST telephone (when enabled)
    +--> Reticulum stack (interfaces, paths, announces)
```

The same backend code powers Docker images, Python wheels, Linux packages, Electron desktop builds, and the Android APK. Packaging differs. Behaviour is intended to stay consistent.

In a regular browser (including headless or LAN installs), Meshchat neXt may register a service worker that caches hashed UI assets and the app shell so repeat loads are faster and a hard refresh can still show the boot splash while the local backend restarts. Mesh messaging, identity, and API data still require the Python backend. Electron does not use this service worker path.

## Main areas of the UI

| Area               | Route               | Purpose                                               |
| ------------------ | ------------------- | ----------------------------------------------------- |
| Messages           | /messages           | LXMF direct messaging, folders, attachments           |
| Audio calls        | /call               | LXST voice calls and voicemail                        |
| Contacts           | /contacts           | Telephone contacts and call-related entries           |
| Relay chat         | /relay-chat         | RRC hubs and rooms (when enabled in settings)         |
| Nomad Network      | /nomadnetwork       | Browse remote NomadNet pages and files                |
| Map                | /map                | OpenLayers map, offline tiles, telemetry              |
| Network visualiser | /network-visualiser | Graph view of mesh topology (sidebar Explore)         |
| Tools              | /tools              | Ping, path tools, RNCP, bots, documentation, and more |
| Settings           | /settings           | Theme, language, LXMF, telephone, security            |
| Archives           | /archives           | Versioned snapshots of Nomad pages (sidebar More)     |
| Interfaces         | /interfaces         | Add and manage Reticulum interfaces (sidebar More)    |
| Blocked            | /blocked            | Blocked destinations (sidebar More)                   |
| Identities         | /identities         | Create, import, or switch identities (sidebar More)   |
| About              | /about              | Version, health, backups (sidebar More or footer)     |
| Documentation      | /documentation      | Meshchat neXt guides and the Reticulum manual         |

Relay chat appears only when rrc_enabled is turned on in settings. When enabled, the Relay chat icon can show a red mention count. Messages shows unread conversation count. Calls shows unread missed-call count.

## Documentation in the app

The **Documentation** page has two tabs.

**Meshchat neXt** shows the guides in this bundle. They are markdown files synced from the docs/ directory in the repository and rendered offline inside the app.

**Reticulum** shows the upstream Reticulum manual as pre-built HTML. It is bundled at build time. You can upload a newer manual ZIP if you need a different version.

Use the search bar to query both sets at once. Meshchat neXt guide text is currently available in English. The Reticulum manual body is English. Localized landing pages exist for several languages on the Reticulum tab.

## Storage locations

| Data                   | Typical path (CLI default)                                                                 |
| ---------------------- | ------------------------------------------------------------------------------------------ |
| Meshchat neXt app data | ./storage (or --storage-dir / MESHCHAT_STORAGE_DIR)                                        |
| Reticulum config       | ~/.reticulum (or --reticulum-config-dir / MESHCHAT_RETICULUM_CONFIG_DIR)                   |
| Portable bundle        | `<data-dir>/storage` and `<data-dir>/.reticulum` when using --data-dir / MESHCHAT_DATA_DIR |
| Desktop Electron data  | ~/.meshchat-next and ~/.reticulum unless overridden at launch                              |
| Per-identity database  | `<storage>/identities/<identity_hash>/database.db`                                         |
| Docker volume          | meshchatnext-config mounted at /config                                                     |

Legacy upstream data may still exist under ~/.reticulum-meshchat/. Migration tooling can move you to the Meshchat neXt layout.

## Where to go next

- **Installation and setup** covers Docker, wheels, desktop packages, and CLI flags.
- **Building from source and packaging** covers offline builds, docker/Dockerfile.build, and Android APKs.
- **Development** covers task/make, version sync, and adding locales.
- **Architecture and design** explains backend managers, identity scoping, and the API model.
- **LXMF messaging** and **Audio calls** describe day-to-day communication features.
- **Identities, privacy, and security** covers backups and corruption recovery.
- **Reticulum interfaces** explains how your node joins the mesh.
- Platform guides under **Platform guides** cover Raspberry Pi, Android Termux, Meta Quest, and Linux sandboxing (Firejail and Bubblewrap).

For protocol-level detail, open the **Reticulum** tab in Documentation or visit the [Reticulum manual](https://reticulum.network/manual/) online.

## Support and community

Use **Meshchat neXt Relay** over Reticulum at `ef933cd2c155bbef703fdf59100598a8`:

- [Bug reports](meshchatnext://relay?hub=ef933cd2c155bbef703fdf59100598a8&room=bug%20reports&name=Meshchat%20neXt%20Relay)
- [Feature requests & suggestions](meshchatnext://relay?hub=ef933cd2c155bbef703fdf59100598a8&room=feature%20requests%20%26%20suggestions&name=Meshchat%20neXt%20Relay)
- [General chat](meshchatnext://relay?hub=ef933cd2c155bbef703fdf59100598a8&room=general&name=Meshchat%20neXt%20Relay)

Open **About → Contact / Support** to join a room or copy its link. Include your version, platform and reproduction steps in bug reports, and review diagnostics for private information before posting. Opening a room does not submit a report. GitHub reporting remains supported through the release's configured `bug_report_url`; the configured destination is [hk1200/Meshchat-neXt Issues](https://github.com/hk1200/Meshchat-neXt/issues). Official downloads are listed on the repository’s Releases page.
