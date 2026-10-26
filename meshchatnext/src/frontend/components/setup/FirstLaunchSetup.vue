<!-- SPDX-License-Identifier: 0BSD -->
<template>
    <component
        :is="isPage ? 'div' : AppModal"
        v-if="isPage || visible"
        :model-value="visible"
        :fullscreen="true"
        :persistent="true"
        :show-close="false"
        body-class="flex flex-1 min-h-0 overflow-hidden"
        panel-class="bg-sem-canvas text-sem-fg h-full! max-h-full! min-h-0"
        class="flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden"
    >
        <div class="flex h-full min-h-0 flex-1 flex-col overflow-hidden bg-sem-canvas text-sem-fg">
            <div
                ref="setupScroll"
                data-testid="setup-scroll"
                tabindex="0"
                aria-label="Setup content"
                class="min-h-0 flex-1 overflow-y-auto overscroll-contain p-4 sm:p-6"
            >
                <div class="max-w-3xl mx-auto space-y-5 pb-6">
                    <header class="flex items-center gap-3 min-w-0">
                        <img :src="logo" alt="" class="size-8 sm:size-12 shrink-0" />
                        <div class="flex-1 min-w-0">
                            <h1 class="text-lg sm:text-2xl font-bold leading-tight">Set up Meshchat neXt</h1>
                            <p class="text-sm text-sem-fg-muted">
                                {{ index + 1 }} of {{ steps.length }} · {{ titles[step] }}
                            </p>
                        </div>
                        <LanguageSelector />
                    </header>
                    <progress
                        :value="index + 1"
                        :max="steps.length"
                        class="w-full h-1.5 accent-sem-accent"
                        aria-label="Setup progress"
                    />
                    <section :key="step" class="space-y-4" :aria-label="titles[step]">
                        <template v-if="step === 'networks'">
                            <h2 class="text-xl font-semibold">What would you like to use?</h2>
                            <p class="text-sm text-sem-fg-muted">
                                New to mesh networking or bringing an existing setup? Choose what you need. We’ll only
                                show the relevant steps, and you can change these choices later in Settings.
                            </p>
                            <label
                                v-for="network in networks"
                                :key="network.id"
                                class="flex gap-3 items-start rounded-xl border border-sem-border bg-sem-surface p-4 cursor-pointer"
                                ><input v-model="choices[network.id]" type="checkbox" class="mt-1 size-5" /><span
                                    ><strong>{{ network.label }}</strong
                                    ><span class="block text-sm text-sem-fg-muted">{{
                                        network.description
                                    }}</span></span
                                ></label
                            >
                            <p class="text-xs text-sem-fg-muted">
                                Reticulum and MeshCore use separate radio connections and identities. SIP uses an
                                internet connection and your own extension account.
                            </p>
                            <details class="rounded-xl border border-sem-border p-4">
                                <summary class="cursor-pointer text-sm font-medium">
                                    Already have a setup or backup?
                                </summary>
                                <div class="text-sm text-sem-fg-muted space-y-2 pt-3">
                                    <p>
                                        Reticulum: import a raw identity key file or a Base32 identity export in the
                                        next step. This restores your address, not another app’s entire database.
                                    </p>
                                    <p>
                                        MeshCore: keep the identity, contacts and channels already stored on your
                                        client, or preview an official MeshCore JSON backup after connecting it.
                                        Encrypted neXt identity backups are also supported.
                                    </p>
                                    <p>
                                        Other formats are not assumed compatible. Keep your original backup; importing
                                        here does not delete it.
                                    </p>
                                </div>
                            </details>
                            <details v-if="migration?.show_choice" class="rounded-xl border border-sem-border p-4">
                                <summary class="cursor-pointer font-medium">Previous installation found</summary>
                                <p class="text-sm text-sem-fg-muted py-3">
                                    You can migrate its existing data into this separate release. The app will restart
                                    if needed.
                                </p>
                                <button class="secondary-chip" :disabled="busy" @click="migrate">
                                    Import previous installation
                                </button>
                            </details>
                            <details v-if="storage?.needs_setup_choice" class="rounded-xl border border-sem-border p-4">
                                <summary class="cursor-pointer font-medium">App storage location</summary>
                                <p class="text-sm text-sem-fg-muted py-3">
                                    Choose where this app keeps its data. App-managed storage works without choosing a
                                    folder.
                                </p>
                                <select v-model="storageMode" class="input-field">
                                    <option value="internal">App-managed internal storage</option>
                                    <option value="external">App-specific external storage</option></select
                                ><button class="secondary-chip mt-3" :disabled="busy" @click="applyStorage">
                                    Apply storage choice
                                </button>
                            </details>
                        </template>
                        <template v-else-if="step === 'identity'">
                            <h2 class="text-xl font-semibold">Your Reticulum identity</h2>
                            <p class="text-sm text-sem-fg-muted">
                                An identity gives you your messaging and calling addresses. Keep the one already on this
                                device, or bring your existing key.
                            </p>
                            <label class="block text-sm"
                                >Display name<input
                                    v-model="name"
                                    class="input-field"
                                    maxlength="100"
                                    autocomplete="nickname"
                            /></label>
                            <label class="block text-sm"
                                >Identity<select v-model="identityMode" class="input-field">
                                    <option value="keep">Use this device’s identity</option>
                                    <option value="file">Import an identity key file</option>
                                    <option value="base32">Import a Base32 identity</option>
                                </select></label
                            >
                            <label v-if="identityMode === 'file'" class="block text-sm"
                                >Identity file<input type="file" class="input-field" @change="chooseIdentity"
                            /></label>
                            <label v-if="identityMode === 'base32'" class="block text-sm"
                                >Private identity export<textarea
                                    v-model="identityKey"
                                    class="input-field font-mono"
                                    autocomplete="off"
                                    spellcheck="false"
                                    rows="3"
                                />
                            </label>
                            <p v-if="identityMode !== 'keep'" class="text-xs text-sem-fg-muted">
                                Only import your own private identity export. Public contact addresses cannot restore an
                                account. The key stays on this device, and your current identity is kept as a separate
                                identity.
                            </p>
                        </template>
                        <template v-else-if="step === 'reticulum'">
                            <h2 class="text-xl font-semibold">Connect Reticulum</h2>
                            <p class="text-sm text-sem-fg-muted">
                                Use a radio, your local network, the internet, or a combination. Existing interfaces are
                                kept.
                            </p>
                            <label class="flex items-start gap-3 rounded-xl border border-sem-border p-4"
                                ><input v-model="internet" type="checkbox" class="mt-1" /><span
                                    ><strong>Internet · TCP</strong
                                    ><span class="block text-sm text-sem-fg-muted"
                                        >Recommended entry point: rmap.world. We’ll add the connection automatically
                                        when you continue.</span
                                    ></span
                                ></label
                            >
                            <details v-if="internet" class="text-sm">
                                <summary class="cursor-pointer">Server details · {{ host }}:{{ port }}</summary>
                                <div class="grid grid-cols-2 gap-3 pt-3">
                                    <label>Host<input v-model="host" class="input-field" /></label
                                    ><label
                                        >Port<input
                                            v-model.number="port"
                                            type="number"
                                            min="1"
                                            max="65535"
                                            class="input-field"
                                    /></label>
                                </div>
                                <a
                                    href="https://rmap.world/services.html"
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    class="text-sem-accent"
                                    >About rmap.world</a
                                >
                            </details>
                            <label class="flex items-start gap-3 rounded-xl border border-sem-border p-4"
                                ><input v-model="local" type="checkbox" class="mt-1" /><span
                                    ><strong>Nearby devices on the same network</strong
                                    ><span class="block text-sm text-sem-fg-muted"
                                        >Adds automatic discovery over your local Wi-Fi or Ethernet network. Internet
                                        service is not required.</span
                                    ></span
                                ></label
                            >
                            <RNodeSetup @busy="childBusy = $event" />
                            <p class="text-xs text-sem-fg-muted">
                                Ordinary announces will be accepted from all connected Reticulum interfaces, including
                                TCP. Bootstrap-only filtering will be turned off; existing interface boundaries and
                                private network settings are kept. Devices still need to be reachable through those
                                interfaces.
                            </p>
                            <p class="text-xs text-sem-fg-muted">
                                TCP uses the device’s available internet connection, including Wi-Fi or mobile data.
                                Tor, I2P and other advanced interfaces can be added later under Interfaces.
                            </p>
                        </template>
                        <template v-else-if="step === 'meshcore'">
                            <h2 class="text-xl font-semibold">Connect your MeshCore client</h2>
                            <p class="text-sm text-sem-fg-muted">
                                A client / companion node connects by Bluetooth or USB. A repeater or room server is not
                                the client radio. Close any other app using this same radio before connecting.
                            </p>
                            <p v-if="!snapshot.available" class="text-sm text-sem-fg-muted">
                                MeshCore radio connections are unavailable on this host. You can finish now and connect
                                from a supported device later.
                            </p>
                            <label class="block text-sm"
                                >Starting point<select v-model="meshStart" class="input-field">
                                    <option value="keep">Use my client’s existing setup</option>
                                    <option value="import">Import a MeshCore backup</option>
                                </select></label
                            >
                            <div
                                v-if="meshStart === 'import'"
                                class="rounded-xl border border-sem-border p-4 space-y-3"
                            >
                                <p class="text-sm text-sem-fg-muted">
                                    Choose an official companion JSON export or a supported multi-device JSON archive.
                                    Select one client at a time; the preview lists the identity, contacts, channels and
                                    settings that can be restored. The file may contain private keys—keep it safe.
                                </p>
                                <MeshCoreBackups
                                    import-only
                                    :snapshot="snapshot"
                                    :disabled="childBusy"
                                    @busy="backupBusy = $event"
                                    @device-hint="onBackupHint"
                                    @changed="onBackupChanged"
                                />
                            </div>
                            <p v-if="deviceHint" class="text-sm text-sem-fg-muted">
                                Backup radio: {{ deviceHint.target }}. If another client is connected, disconnect it
                                first. Pair this radio in system Bluetooth settings if needed. It only connects when you
                                tap Connect MeshCore.
                            </p>
                            <MeshCoreSettings
                                setup-mode
                                :suggested-connection="deviceHint"
                                @busy="childBusy = $event"
                            />
                            <details v-if="snapshot.connected" class="rounded-xl border border-sem-border p-4">
                                <summary class="cursor-pointer font-medium">
                                    Name your MeshCore client · optional
                                </summary>
                                <MeshCoreIdentitySettings
                                    :snapshot="snapshot"
                                    @busy="childBusy = $event"
                                    @saved="refresh"
                                />
                            </details>
                            <p class="text-xs text-sem-fg-muted">
                                Existing radio settings are read, not replaced. Check your local group’s frequency,
                                bandwidth, SF and CR before changing the primary profile. MeshCore does not require
                                internet access for radio messaging.
                            </p>
                        </template>
                        <template v-else-if="step === 'radio2'">
                            <h2 class="text-xl font-semibold">Optional photos and voice · Radio2</h2>
                            <p class="text-sm text-sem-fg-muted">
                                Standard MeshCore firmware is enough for text DMs, channels and supported node tools.
                                You do not need Radio2 to use neXt.
                            </p>
                            <p class="text-sm text-sem-fg-muted">
                                MediaMesh photos and recorded voice clips need Radio2-compatible companion firmware on
                                both client nodes. Radio2 is a second profile on the same transceiver, not a second
                                physical radio. It does not add live phone calls.
                            </p>
                            <label class="block text-sm"
                                >Which setup will you use?<select v-model="radioChoice" class="input-field">
                                    <option value="keep">Keep my current setup / decide later</option>
                                    <option value="standard">Standard MeshCore messaging · Radio2 off</option>
                                    <option value="media">Radio2-compatible firmware · enable media</option>
                                </select></label
                            >
                            <label v-if="radioChoice === 'media'" class="block text-sm"
                                >Media profile<select v-model="mediaProfile" class="input-field">
                                    <option value="keep">Keep the radio’s saved Radio2 profile</option>
                                    <option value="us915">US MediaMesh · 911.150 MHz / 250 kHz / SF7 / CR4/5</option>
                                </select></label
                            >
                            <p v-if="radioChoice === 'media'" class="text-xs text-sem-fg-muted">
                                Choose the profile your local group uses and confirm it is appropriate for your region.
                                Primary radio frequency and power are preserved. neXt checks support, disables crossing
                                and routes media over Radio2 only.
                            </p>
                            <details class="rounded-xl border border-sem-border p-4">
                                <summary class="cursor-pointer font-medium">Firmware and compatibility help</summary>
                                <div class="pt-3 space-y-2 text-sm text-sem-fg-muted">
                                    <p>
                                        Choose the companion build for your exact board, radio module and Bluetooth/USB
                                        connection. Standard companion builds may not include Radio2. Back up the client
                                        before changing firmware.
                                    </p>
                                    <a
                                        :href="RADIO2_FIRMWARE_URL"
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        class="block text-sem-accent"
                                        >Radio2 / Cascade companion firmware downloads</a
                                    ><a
                                        :href="RADIO2_GUIDE_URL"
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        class="block text-sem-accent"
                                        >MediaMesh setup and firmware guide</a
                                    >
                                    <p>
                                        Without compatible firmware, radio text still works, however MediaMesh photo and
                                        audio transfers will be unavailable.
                                    </p>
                                    <p>
                                        MediaMesh audio and images are unencrypted over radio, even when the announcing
                                        DM is encrypted. Compatible peers and radio reachability are also required.
                                    </p>
                                </div>
                            </details>
                        </template>
                        <template v-else-if="step === 'sip'">
                            <h2 class="text-xl font-semibold">SIP extension calling · optional</h2>
                            <p class="text-sm text-sem-fg-muted">
                                Use your own extension and password. The editable HOIP server preset is ready; no
                                account is included. HOIP calls other extensions, not ordinary telephone numbers. You
                                can skip this and configure it later under Settings → SIP.
                            </p>
                            <SipPhone mode="settings" @busy="childBusy = $event" />
                        </template>
                        <template v-else-if="step === 'ready'">
                            <h2 class="text-xl font-semibold">Ready to use neXt</h2>
                            <p class="text-sm text-sem-fg-muted">
                                Your choices are saved. You can revisit this guide or change networks under Settings →
                                App features.
                            </p>
                            <ul class="space-y-3 text-sm">
                                <li v-if="choices.reticulum">
                                    <strong>Reticulum</strong> · Messages and LXST calls use your Reticulum identity.
                                    Announces from connected interfaces appear under Messages → Announces → Reticulum.
                                </li>
                                <li v-if="choices.meshcore">
                                    <strong>MeshCore</strong> ·
                                    {{
                                        snapshot.connected
                                            ? "Client connected."
                                            : "Client connection can be completed later."
                                    }}
                                    DMs appear in Messages; channels and saved nodes are in the sidebar. Discover nearby
                                    users under Announces → MeshCore.
                                </li>
                                <li v-if="choices.sip">
                                    <strong>SIP</strong> · Accounts are under Settings → SIP; extension calls are in
                                    Telephone.
                                </li>
                            </ul>
                            <p class="text-sm text-sem-fg-muted">
                                Contacts stay separate across networks unless you explicitly link them. Enable location
                                sharing or send an announce only when you want to; setup does not publish your location.
                            </p>
                        </template>
                        <SetupHelp :topic="step" />
                    </section>
                    <p
                        v-if="error"
                        role="alert"
                        class="rounded-lg border border-sem-danger p-3 text-sm text-sem-danger"
                    >
                        {{ error }}
                    </p>
                    <p v-if="notice" role="status" class="text-sm text-sem-accent">{{ notice }}</p>
                </div>
            </div>
            <footer
                class="shrink-0 border-t border-sem-border bg-sem-canvas px-4 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] sm:px-6"
            >
                <div class="max-w-3xl mx-auto flex flex-wrap items-center gap-3">
                    <button data-app-back type="button" class="secondary-chip" :disabled="working" @click="previous">
                        Back</button
                    ><button
                        v-if="step !== 'ready'"
                        type="button"
                        class="text-sm text-sem-fg-muted"
                        :disabled="working"
                        @click="later"
                    >
                        Set up later</button
                    ><button type="button" class="primary-chip ml-auto" :disabled="working" @click="next">
                        {{ working ? "Working…" : step === "ready" ? "Start using neXt" : "Continue" }}
                    </button>
                </div>
            </footer>
        </div>
    </component>
</template>
<script setup>
import { computed, ref, onMounted, onBeforeUnmount, watch, nextTick } from "vue";
import { useRoute, useRouter, onBeforeRouteLeave } from "vue-router";
import AppModal from "../AppModal.vue";
import LanguageSelector from "../LanguageSelector.vue";
import MeshCoreSettings from "../meshcore/MeshCoreSettings.vue";
import MeshCoreBackups from "../meshcore/MeshCoreBackups.vue";
import MeshCoreIdentitySettings from "../meshcore/MeshCoreIdentitySettings.vue";
import SipPhone from "../sip/SipPhone.vue";
import SetupHelp from "./SetupHelp.vue";
import RNodeSetup from "./RNodeSetup.vue";
import AndroidStorageBridge from "../../js/AndroidStorageBridge";
import { appFeatures, setAppFeatures, featureRouteAllowed } from "../../js/appFeatures";
import { useMeshCoreUi } from "../../js/meshcoreUi";
import {
    setupSteps,
    configureReticulumSetup,
    applySetupRadio2,
    RMAP_TCP,
    RADIO2_FIRMWARE_URL,
    RADIO2_GUIDE_URL,
    SETUP_DRAFT_KEY,
} from "../../js/firstLaunchSetup";
import { apiPath, EMITTER_EVENTS } from "../../js/constants";
import { useConfigStore } from "../../js/stores/configStore";
import GlobalEmitter from "../../js/GlobalEmitter";
import logo from "../../assets/images/logo.png";
const props = defineProps({ page: { type: Boolean, default: false } });
const route = useRoute() || { meta: {}, query: {} },
    router = useRouter();
const visible = ref(false),
    isPage = computed(() => props.page),
    choices = ref({ ...appFeatures }),
    index = ref(0),
    busy = ref(false),
    childBusy = ref(false),
    backupBusy = ref(false),
    error = ref(""),
    notice = ref("");
const steps = computed(() => setupSteps(choices.value)),
    step = computed(() => steps.value[index.value] || "ready"),
    working = computed(() => busy.value || childBusy.value || backupBusy.value);
const setupScroll = ref(null);
watch(step, async () => {
    await nextTick();
    if (setupScroll.value) {
        setupScroll.value.scrollTop = 0;
        setupScroll.value.focus({ preventScroll: true });
    }
});
let allowLeave = false;
const backupDone = ref(false);
const meshStart = ref("keep"),
    deviceHint = ref(null);
const pendingIdentity = ref("");
const name = ref(""),
    identityMode = ref("keep"),
    identityKey = ref(""),
    identityFile = ref(null),
    internet = ref(false),
    local = ref(false),
    host = ref(RMAP_TCP.host),
    port = ref(RMAP_TCP.port),
    radioChoice = ref("keep"),
    mediaProfile = ref("keep"),
    migration = ref(null),
    storage = ref(null),
    storageMode = ref("internal");
const storageBridge = new AndroidStorageBridge();
const { snapshot, refresh } = useMeshCoreUi(
    () => null,
    () => visible.value && choices.value.meshcore && ["meshcore", "radio2", "ready"].includes(step.value)
);
const titles = {
    networks: "Choose networks",
    identity: "Reticulum identity",
    reticulum: "Reticulum connections",
    meshcore: "MeshCore client",
    radio2: "Optional media",
    sip: "SIP account",
    ready: "Finish",
};
const networks = [
    {
        id: "reticulum",
        label: "Reticulum",
        description: "Messages and calls over RNode radios, local networks or internet connections.",
    },
    {
        id: "meshcore",
        label: "MeshCore",
        description:
            "Text messages, channels and nodes through a MeshCore companion radio; optional media with compatible firmware.",
    },
    {
        id: "sip",
        label: "SIP",
        description: "Internet extension calling, including HOIP. An existing account is required.",
    },
];
function saveDraft() {
    localStorage.setItem(
        SETUP_DRAFT_KEY,
        JSON.stringify({
            step: step.value,
            pendingIdentity: pendingIdentity.value,
            choices: choices.value,
            internet: internet.value,
            local: local.value,
            host: host.value,
            port: port.value,
            radioChoice: radioChoice.value,
            mediaProfile: mediaProfile.value,
        })
    );
}
function clearSecrets() {
    identityKey.value = "";
    identityFile.value = null;
}
async function show() {
    allowLeave = false;
    visible.value = true;
    error.value = "";
    try {
        const draft = JSON.parse(localStorage.getItem(SETUP_DRAFT_KEY) || "null");
        if (draft) {
            pendingIdentity.value = /^[0-9a-f]{32,64}$/i.test(draft.pendingIdentity || "") ? draft.pendingIdentity : "";
            choices.value = {
                ...appFeatures,
                ...Object.fromEntries(
                    Object.entries(draft.choices || {}).filter(
                        ([key, value]) => ["reticulum", "meshcore", "sip"].includes(key) && typeof value === "boolean"
                    )
                ),
            };
            internet.value = draft.internet === true;
            local.value = draft.local === true;
            host.value = typeof draft.host === "string" ? draft.host : RMAP_TCP.host;
            port.value = Number(draft.port) || RMAP_TCP.port;
            radioChoice.value = ["keep", "standard", "media"].includes(draft.radioChoice) ? draft.radioChoice : "keep";
            mediaProfile.value = draft.mediaProfile === "us915" ? "us915" : "keep";
            index.value = Math.max(0, steps.value.indexOf(draft.step));
        }
    } catch {
        index.value = 0;
    }
    try {
        const { data } = await window.api.get(apiPath("/config"));
        name.value = data.config?.display_name || "";
    } catch {
        notice.value = "Existing settings could not be read yet. You can retry setup later.";
    }
    try {
        migration.value = (await window.api.get(apiPath("/app/info"))).data.app_info?.migration || null;
    } catch {
        /* optional migration offer */
    }
    if (isPage.value) {
        const requested = steps.value.indexOf(route.query?.setupStep);
        if (requested >= 0) index.value = requested;
        await router.replace({ query: { ...route.query, setupStep: step.value } });
    }
    storage.value = storageBridge.getStatus();
    storageMode.value = storage.value?.active_mode === "external" ? "external" : "internal";
}
function chooseIdentity(event) {
    identityFile.value = event.target.files?.[0] || null;
    if (identityFile.value?.size > 65536) {
        error.value = "Choose an identity key file, not a full app archive.";
        identityFile.value = null;
    }
}
async function saveIdentity() {
    if (pendingIdentity.value) {
        await activatePendingIdentity();
        return;
    }
    if (identityMode.value === "keep") {
        if (name.value.trim()) {
            const { data } = await window.api.patch(apiPath("/config"), { display_name: name.value.trim() });
            if (data.config) useConfigStore().config = data.config;
        }
        return;
    }
    let data;
    if (identityMode.value === "file") {
        if (!identityFile.value) throw new Error("Choose your private identity file.");
        const form = new FormData();
        form.append("file", identityFile.value);
        if (name.value.trim()) form.append("display_name", name.value.trim());
        data = (await window.api.post(apiPath("/identity/restore"), form)).data;
    } else {
        const key = identityKey.value.replace(/\s+/g, "");
        if (!key) throw new Error("Enter your Base32 private identity export.");
        data = (
            await window.api.post(apiPath("/identity/restore"), {
                base32: key,
                display_name: name.value.trim() || undefined,
            })
        ).data;
    }
    const hash = data.identity?.hash;
    if (!hash) throw new Error("The identity import was not confirmed.");
    clearSecrets();
    identityMode.value = "keep";
    saveDraft();
    pendingIdentity.value = hash;
    saveDraft();
    await activatePendingIdentity();
}
async function activatePendingIdentity() {
    const hash = pendingIdentity.value;
    const identities = (await window.api.get(apiPath("/identities"))).data.identities || [];
    if (identities.some((identity) => identity.is_current && identity.hash === hash)) {
        pendingIdentity.value = "";
        saveDraft();
        return;
    }
    GlobalEmitter.emit(EMITTER_EVENTS.IDENTITY_SWITCHING_START);
    try {
        const result = (await window.api.post(apiPath("/identities/switch"), { identity_hash: hash })).data;
        if (!result.hotswapped) {
            GlobalEmitter.emit(EMITTER_EVENTS.IDENTITY_SWITCHING_ABORT);
            throw new Error("Identity imported. Restart the app to activate it, then continue setup.");
        }
        pendingIdentity.value = "";
        saveDraft();
        GlobalEmitter.emit(EMITTER_EVENTS.IDENTITY_SWITCHED_APPLY, {
            identity_hash: result.identity_hash || hash,
            display_name: result.display_name || name.value,
            requires_reauth: Boolean(result.requires_reauth),
        });
    } catch (error) {
        GlobalEmitter.emit(EMITTER_EVENTS.IDENTITY_SWITCHING_ABORT);
        throw error;
    }
}

function onBackupHint(hint) {
    deviceHint.value = hint;
    backupDone.value = false;
}
function onBackupChanged(result) {
    backupDone.value = result?.state === "complete";
    refresh();
}
async function next() {
    if (working.value) return;
    busy.value = true;
    error.value = "";
    notice.value = "";
    try {
        if (step.value === "networks") setAppFeatures(choices.value);
        if (step.value === "identity") await saveIdentity();
        if (step.value === "reticulum")
            await configureReticulumSetup(window.api, {
                internet: internet.value,
                local: local.value,
                host: host.value,
                port: port.value,
            });
        if (step.value === "meshcore" && meshStart.value === "import" && !backupDone.value)
            throw new Error(
                "Preview and apply your backup first, or choose to use the client’s existing setup. You can also finish setup later."
            );
        if (step.value === "radio2")
            await applySetupRadio2(
                window.api,
                radioChoice.value,
                snapshot.value.connected ? snapshot.value.owner : null,
                mediaProfile.value
            );
        if (step.value === "ready") {
            await finish();
            return;
        }
        index.value++;
        saveDraft();
        if (isPage.value) await router.push({ query: { ...route.query, setupStep: step.value } });
    } catch (e) {
        error.value =
            e.response?.data?.message ||
            e.response?.data?.error ||
            e.message ||
            "Setup could not save this step. Your existing settings are kept.";
    } finally {
        busy.value = false;
    }
}
function previous(updateHistory = true) {
    if (working.value) return;
    if (index.value === 0) {
        notice.value =
            "You’re at the start of setup. Choose Set up later to leave; you can reopen it in Settings → App features → Run setup guide.";
        return;
    }
    index.value = Math.max(0, index.value - 1);
    error.value = "";
    notice.value = "";
    saveDraft();
    if (isPage.value && updateHistory) void router.replace({ query: { ...route.query, setupStep: step.value } });
}
watch(
    () => route.query?.setupStep,
    (value) => {
        const target = steps.value.indexOf(value);
        if (isPage.value && target >= 0 && !working.value) {
            index.value = target;
            saveDraft();
        }
    }
);
if (isPage.value)
    onBeforeRouteLeave(() => {
        if (allowLeave || !visible.value) return true;
        if (!working.value && index.value > 0) previous(false);
        else if (!working.value)
            notice.value =
                "You’re at the start of setup. Choose Set up later to leave; you can reopen it in Settings → App features → Run setup guide.";
        return false;
    });
async function finish() {
    await window.api.post(apiPath("/app/tutorial/seen"));
    localStorage.removeItem(SETUP_DRAFT_KEY);
    clearSecrets();
    allowLeave = true;
    visible.value = false;
    GlobalEmitter.emit(EMITTER_EVENTS.TUTORIAL_FINISHED);
    if (isPage.value || !featureRouteAllowed(route))
        await router.push({
            name:
                choices.value.reticulum || choices.value.meshcore
                    ? "messages"
                    : choices.value.sip
                      ? "call"
                      : "feature-settings",
            ...(choices.value.sip && !choices.value.reticulum && !choices.value.meshcore
                ? { query: { network: "sip" } }
                : {}),
        });
}
async function later() {
    if (working.value) return;
    busy.value = true;
    error.value = "";
    try {
        setAppFeatures(choices.value);
        await finish();
    } catch {
        error.value = "Could not save setup completion. Please try again.";
    } finally {
        busy.value = false;
    }
}
async function migrate() {
    if (working.value) return;
    busy.value = true;
    try {
        saveDraft();
        await window.api.post(apiPath("/setup/storage-migration"), { action: "migrate" });
        if (window.electron?.relaunch) await window.electron.relaunch();
        else notice.value = "Migration requested. Restart the app to continue.";
    } catch {
        error.value = "Migration could not complete. Your previous installation is kept.";
    } finally {
        busy.value = false;
    }
}
function applyStorage() {
    try {
        saveDraft();
        const result = storageBridge.applySetupChoice(storageMode.value, storage.value);
        if (result.restarted) notice.value = "Storage choice saved. The app is restarting.";
        else storage.value = storageBridge.getStatus();
    } catch {
        error.value = "Storage location could not be changed.";
    }
}
watch(visible, (value) => {
    if (!value) clearSecrets();
});
onMounted(() => {
    if (isPage.value) show();
});
onBeforeUnmount(clearSecrets);
defineExpose({ show, visible });
</script>
<style scoped>
@reference "../../style.css";
.input-field {
    @apply block w-full rounded-lg border border-sem-border bg-sem-surface px-3 py-2 text-sem-fg mt-1;
}
button {
    @apply disabled:opacity-50 disabled:cursor-not-allowed;
}
</style>
