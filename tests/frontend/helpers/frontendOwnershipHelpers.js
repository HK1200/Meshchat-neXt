// SPDX-License-Identifier: 0BSD

import { existsSync, readdirSync, readFileSync, writeFileSync, statSync } from "fs";
import { join, relative } from "path";

export function repoRootFromCwd(cwd = process.cwd()) {
    return cwd;
}

export function readUtf8(absolutePath) {
    return readFileSync(absolutePath, "utf8");
}

export function listFilesRecursive(dir, exts) {
    const out = [];
    if (!existsSync(dir)) {
        return out;
    }
    for (const name of readdirSync(dir)) {
        const full = join(dir, name);
        const st = statSync(full);
        if (st.isDirectory()) {
            out.push(...listFilesRecursive(full, exts));
            continue;
        }
        if (exts.some((ext) => name.endsWith(ext))) {
            out.push(full);
        }
    }
    return out;
}

export function joinFeatureSources(repoRoot, relativeDirs) {
    const chunks = [];
    for (const rel of relativeDirs) {
        const abs = join(repoRoot, rel);
        if (statSync(abs, { throwIfNoEntry: false })?.isFile()) {
            chunks.push(readUtf8(abs));
            continue;
        }
        for (const file of listFilesRecursive(abs, [".vue", ".js"])) {
            chunks.push(readUtf8(file));
        }
    }
    return chunks.join("\n");
}

export function discoverMegaPageOwnership(repoRoot) {
    const pages = [
        {
            id: "settings",
            shell: "meshchatnext/src/frontend/components/settings/SettingsPage.vue",
            allowed_child_dirs: [
                "meshchatnext/src/frontend/components/settings/sections",
                "meshchatnext/src/frontend/js/settings",
            ],
            required_children: [
                "meshchatnext/src/frontend/components/settings/SettingToggleRow.vue",
                "meshchatnext/src/frontend/components/settings/SettingsSectionBlock.vue",
                "meshchatnext/src/frontend/components/settings/sections/LanguageSettingsSection.vue",
                "meshchatnext/src/frontend/components/settings/sections/DesktopSettingsSection.vue",
                "meshchatnext/src/frontend/components/settings/sections/StrangerProtectionSettingsSection.vue",
                "meshchatnext/src/frontend/components/settings/sections/BanishmentSettingsSection.vue",
                "meshchatnext/src/frontend/components/settings/sections/StickersSettingsSection.vue",
                "meshchatnext/src/frontend/components/settings/sections/GifsSettingsSection.vue",
                "meshchatnext/src/frontend/components/settings/sections/TelephonySettingsSection.vue",
                "meshchatnext/src/frontend/components/settings/sections/AppearanceSettingsSection.vue",
                "meshchatnext/src/frontend/components/settings/sections/BatterySettingsSection.vue",
                "meshchatnext/src/frontend/components/settings/sections/VisualiserSettingsSection.vue",
                "meshchatnext/src/frontend/components/settings/sections/BlockedSettingsSection.vue",
                "meshchatnext/src/frontend/components/settings/sections/AndroidSettingsSection.vue",
                "meshchatnext/src/frontend/components/settings/sections/ArchiverSettingsSection.vue",
                "meshchatnext/src/frontend/components/settings/PluginsSettingsSection.vue",
            ],
            required_shell_imports: [
                "LanguageSettingsSection",
                "DesktopSettingsSection",
                "StrangerProtectionSettingsSection",
                "BanishmentSettingsSection",
                "StickersSettingsSection",
                "GifsSettingsSection",
                "TelephonySettingsSection",
                "AppearanceSettingsSection",
                "BatterySettingsSection",
                "VisualiserSettingsSection",
                "BlockedSettingsSection",
                "AndroidSettingsSection",
                "ArchiverSettingsSection",
                "PluginsSettingsSection",
                "SettingsSectionBlock",
            ],
        },
        {
            id: "map",
            shell: "meshchatnext/src/frontend/components/map/MapPage.vue",
            allowed_child_dirs: ["meshchatnext/src/frontend/components/map/internal", "meshchatnext/src/frontend/js"],
            required_children: [
                "meshchatnext/src/frontend/components/map/internal/MapClusterPanel.vue",
                "meshchatnext/src/frontend/components/map/internal/MapMarkerPanel.vue",
                "meshchatnext/src/frontend/components/map/internal/MapDrawingToolbar.vue",
                "meshchatnext/src/frontend/components/map/internal/MapBearingInstructions.vue",
                "meshchatnext/src/frontend/components/map/internal/MapSearchBar.vue",
                "meshchatnext/src/frontend/components/map/internal/MapExportInstructions.vue",
                "meshchatnext/src/frontend/components/map/internal/MapExportConfigPanel.vue",
                "meshchatnext/src/frontend/components/map/internal/MapExportProgressPanel.vue",
                "meshchatnext/src/frontend/components/map/internal/MapLoadingOverlay.vue",
                "meshchatnext/src/frontend/components/map/internal/MapSidePanel.vue",
                "meshchatnext/src/frontend/components/map/internal/MapDiscoverPanel.vue",
                "meshchatnext/src/frontend/components/map/internal/MapPublishPanel.vue",
                "meshchatnext/src/frontend/components/map/internal/MapLayersPanel.vue",
                "meshchatnext/src/frontend/components/map/internal/MapOfflinePanel.vue",
                "meshchatnext/src/frontend/components/map/internal/MapVectorExchangePanel.vue",
                "meshchatnext/src/frontend/components/map/internal/MapRemoteOverlayPanel.vue",
                "meshchatnext/src/frontend/components/map/internal/MapSaveDrawingModal.vue",
                "meshchatnext/src/frontend/components/map/internal/MapLoadDrawingModal.vue",
                "meshchatnext/src/frontend/components/map/internal/MapMobileNoteModal.vue",
                "meshchatnext/src/frontend/components/map/internal/clusterUtils.js",
                "meshchatnext/src/frontend/components/map/internal/discoveredIcons.js",
                "meshchatnext/src/frontend/components/map/internal/mapDedupe.js",
                "meshchatnext/src/frontend/components/map/internal/markerStyles.js",
            ],
            required_shell_imports: [
                "MapClusterPanel",
                "MapMarkerPanel",
                "MapDrawingToolbar",
                "MapBearingInstructions",
                "MapSearchBar",
                "MapExportInstructions",
                "MapExportConfigPanel",
                "MapExportProgressPanel",
                "MapLoadingOverlay",
                "MapSidePanel",
                "MapSaveDrawingModal",
                "MapLoadDrawingModal",
                "MapMobileNoteModal",
                "clusterUtils",
                "discoveredIcons",
                "mapDedupe",
                "markerStyles",
            ],
        },
        {
            id: "messages",
            shell: "meshchatnext/src/frontend/components/messages/ConversationViewer.vue",
            allowed_child_dirs: [
                "meshchatnext/src/frontend/components/messages",
                "meshchatnext/src/frontend/components/messages/composer",
                "meshchatnext/src/frontend/components/messages/modals",
                "meshchatnext/src/frontend/components/messages/outbound",
                "meshchatnext/src/frontend/components/messages/lxmf",
                "meshchatnext/src/frontend/components/messages/telemetry",
            ],
            required_children: [
                "meshchatnext/src/frontend/components/messages/ConversationPeerHeader.vue",
                "meshchatnext/src/frontend/components/messages/ConversationMessageEntry.vue",
                "meshchatnext/src/frontend/components/messages/conversationMessageHelpers.js",
                "meshchatnext/src/frontend/components/messages/outbound/OutboundTransferProgressFooter.vue",
                "meshchatnext/src/frontend/components/messages/modals/ShareContactModal.vue",
                "meshchatnext/src/frontend/components/messages/modals/ConversationImageModal.vue",
                "meshchatnext/src/frontend/components/messages/composer/AddImageButton.vue",
                "meshchatnext/src/frontend/components/messages/lxmf/contactDisplay.js",
                "meshchatnext/src/frontend/components/messages/lxmf/normalize.js",
            ],
            required_shell_imports: [
                "ConversationPeerHeader",
                "ConversationMessageEntry",
                "conversationMessageHelpers",
                "ShareContactModal",
                "ConversationImageModal",
                "AddImageButton",
                "contactDisplay",
                "normalize",
            ],
        },
        {
            id: "call",
            shell: "meshchatnext/src/frontend/components/call/CallPage.vue",
            allowed_child_dirs: [
                "meshchatnext/src/frontend/components/call",
                "meshchatnext/src/frontend/components/call/tabs",
                "meshchatnext/src/frontend/components/call/audio",
            ],
            required_children: [
                "meshchatnext/src/frontend/components/call/CallOverlay.vue",
                "meshchatnext/src/frontend/components/call/audio/RingtoneEditor.vue",
                "meshchatnext/src/frontend/components/call/tabs/CallPhonebookTab.vue",
                "meshchatnext/src/frontend/components/call/tabs/CallContactsTab.vue",
                "meshchatnext/src/frontend/components/call/tabs/CallVoicemailTab.vue",
                "meshchatnext/src/frontend/components/call/tabs/CallTabBar.vue",
            ],
            required_shell_imports: [
                "RingtoneEditor",
                "CallPhonebookTab",
                "CallContactsTab",
                "CallVoicemailTab",
                "CallTabBar",
            ],
        },
        {
            id: "app",
            shell: "meshchatnext/src/frontend/components/App.vue",
            allowed_child_dirs: [
                "meshchatnext/src/frontend/components/layout",
                "meshchatnext/src/frontend/components/call",
            ],
            required_children: [
                "meshchatnext/src/frontend/components/layout/AppShellBanners.vue",
                "meshchatnext/src/frontend/components/layout/AppIdentitySwitchOverlay.vue",
                "meshchatnext/src/frontend/components/call/CallOverlay.vue",
            ],
            required_shell_imports: ["AppShellBanners", "AppIdentitySwitchOverlay", "CallOverlay", "listNavItems"],
        },
    ];

    return {
        version: 1,
        pages: pages.map((page) => ({
            ...page,
            required_children: page.required_children.filter((rel) => existsSync(join(repoRoot, rel))),
            required_shell_imports: page.required_shell_imports,
        })),
    };
}

export function writeOwnershipFixture(repoRoot, fixturePath) {
    const payload = discoverMegaPageOwnership(repoRoot);
    writeFileSync(fixturePath, `${JSON.stringify(payload, null, 4)}\n`, "utf8");
    return payload;
}

export function loadJsonFixture(repoRoot, relativePath) {
    return JSON.parse(readUtf8(join(repoRoot, relativePath)));
}

export function assertStringsInSources(sourceText, requiredStrings, label) {
    const missing = requiredStrings.filter((s) => !sourceText.includes(s));
    if (missing.length) {
        throw new Error(`${label} missing required strings: ${missing.join(", ")}`);
    }
}

export function relativeRepoPath(repoRoot, absolutePath) {
    return relative(repoRoot, absolutePath).split("\\").join("/");
}
