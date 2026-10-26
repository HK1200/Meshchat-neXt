<template>
    <section class="border-t border-sem-border pt-4 space-y-4" aria-label="MeshCore backups">
        <h3 class="font-semibold">MeshCore backups</h3>
        <details v-if="!importOnly" @toggle="backupToggled">
            <summary class="cursor-pointer text-sm font-medium">Save encrypted identity backup</summary>
            <form class="space-y-3 pt-3" @submit.prevent="backup">
                <p class="text-xs text-sem-fg-muted">
                    Saves your radio identity in a password-encrypted file. Keep the file and password safe; the
                    password cannot be recovered. This is an identity backup, not a full configuration export.
                </p>
                <label class="block text-sm"
                    >Backup password<input
                        v-model="backupPassword"
                        class="input-field"
                        type="password"
                        autocomplete="new-password"
                        :disabled="operationBusy || disabled"
                        required
                /></label>
                <label class="block text-sm"
                    >Confirm password<input
                        v-model="confirmation"
                        class="input-field"
                        type="password"
                        autocomplete="new-password"
                        :disabled="operationBusy || disabled"
                        required
                /></label>
                <p class="text-xs text-sem-fg-muted">
                    Use 12–1024 characters. Your firmware must allow identity export.
                </p>
                <button
                    class="primary-chip"
                    :disabled="operationBusy || disabled || !snapshot.connected || !passwordValid"
                >
                    {{ exporting ? "Preparing encrypted backup…" : "Download encrypted identity backup" }}
                </button>
                <p v-if="backupNotice" role="status" class="text-sm text-sem-accent">{{ backupNotice }}</p>
                <p v-if="backupError" role="alert" class="text-sm text-sem-danger">{{ backupError }}</p>
            </form>
        </details>
        <details :open="importOnly" @toggle="importToggled">
            <summary class="cursor-pointer text-sm font-medium">Import MeshCore configuration</summary>
            <div class="space-y-3 pt-3">
                <p class="text-xs text-sem-fg-muted">
                    Choose an official MeshCore companion JSON export or an encrypted identity backup from this app.
                    Review what can be imported before changing the radio. Existing contacts and channels are kept.
                </p>
                <label class="block text-sm"
                    >Backup file<input
                        class="input-field"
                        type="file"
                        accept=".json,application/json"
                        :disabled="operationBusy || disabled || uncertainImport"
                        @change="loadFile"
                /></label>
                <p v-if="fileName" class="text-xs text-sem-fg-muted break-all">Loaded: {{ fileName }}</p>
                <p v-if="raw && !snapshot.connected" role="status" class="text-xs text-sem-fg-muted">
                    Connect your MeshCore client to preview and apply this backup. Nothing has been changed on the
                    radio.
                </p>
                <label v-if="deviceChoices.length > 1" class="block text-sm"
                    >Device to restore<select
                        v-model.number="deviceIndex"
                        class="input-field"
                        :disabled="operationBusy || disabled"
                        @change="selectDevice"
                    >
                        <option v-for="(device, index) in deviceChoices" :key="index" :value="index">
                            {{ device.label }}
                        </option>
                    </select></label
                >
                <p v-if="connectionHint" class="text-xs text-sem-fg-muted">
                    Backup radio · {{ connectionHint.target }}. Pair it in Android settings if needed, then connect it
                    to preview the import. Bluetooth pairing keys are not part of this import.
                </p>
                <label v-if="encrypted" class="block text-sm"
                    >Backup password<input
                        v-model="importPassword"
                        class="input-field"
                        type="password"
                        autocomplete="off"
                        :disabled="operationBusy || disabled"
                /></label>
                <button
                    type="button"
                    class="secondary-chip"
                    :disabled="
                        operationBusy || disabled || !raw || !snapshot.connected || (encrypted && !importPassword)
                    "
                    @click="review"
                >
                    {{ working ? "Working…" : "Preview import" }}
                </button>
                <p v-if="importError" role="alert" class="text-sm text-sem-danger">{{ importError }}</p>
                <template v-if="preview">
                    <p class="text-sm font-semibold">Review import · MeshCore</p>
                    <p class="text-xs text-sem-fg-muted">
                        Existing entries with the same public key or channel key are kept. New channels use empty slots;
                        the default channel is protected. Cached routes, app preferences and other unsupported fields
                        are not imported.
                    </p>
                    <label v-for="section in preview.sections" :key="section" class="flex items-start gap-2 text-sm">
                        <input
                            v-model="chosen"
                            type="checkbox"
                            :value="section"
                            :disabled="operationBusy || disabled || locked || Boolean(preview.errors[section])"
                            class="mt-1"
                        />
                        <span
                            >{{ sectionLabel(section)
                            }}<span v-if="preview.errors[section]" class="block text-xs text-sem-danger">{{
                                preview.errors[section]
                            }}</span></span
                        >
                    </label>
                    <p v-if="preview.identity_replacement" class="text-sm text-sem-danger">
                        The backup has a different identity. Selecting Identity will replace this radio's private key.
                        Save the current identity first if you need to keep it.
                    </p>
                    <p v-if="preview.backup_public_key" class="text-xs font-mono break-all text-sem-fg-muted">
                        Backup public address: {{ preview.backup_public_key }}
                    </p>
                    <p
                        v-if="preview.backup_public_key && !preview.sections.includes('identity')"
                        class="text-xs text-sem-fg-muted"
                    >
                        This backup has no private identity key. The selected settings, contacts and channels can be
                        restored, but the connected radio keeps its current identity.
                    </p>
                    <div v-if="preview.unsupported.length" class="text-xs text-sem-fg-muted">
                        <strong>Not applied to the radio:</strong>
                        <ul class="list-disc pl-5">
                            <li v-for="field in preview.unsupported" :key="field">{{ unsupportedLabel(field) }}</li>
                        </ul>
                    </div>
                    <button
                        type="button"
                        class="primary-chip"
                        :disabled="operationBusy || disabled || locked || !chosen.length || !snapshot.connected"
                        @click="apply"
                    >
                        Import selected sections
                    </button>
                </template>
                <div
                    v-if="result"
                    role="status"
                    class="space-y-1 text-sm"
                    :class="result.state === 'complete' ? 'text-sem-accent' : 'text-sem-fg-muted'"
                >
                    <p>
                        {{
                            result.state === "complete"
                                ? "Selected import sections completed and verified."
                                : result.state === "not_found"
                                  ? "No import receipt found. No automatic retry will be made; inspect the radio and make a new preview."
                                  : "Import outcome needs inspection. Completed changes remain; do not assume the whole import succeeded."
                        }}
                    </p>
                    <p v-if="result.completed?.length">Completed: {{ result.completed.join(", ") }}</p>
                    <p v-if="result.stopped_at">Stopped at: {{ result.stopped_at }}</p>
                    <p v-if="result.contacts_added != null">
                        Contacts added: {{ result.contacts_added }} · Channels added: {{ result.channels_added }}
                    </p>
                </div>
                <button
                    v-if="run && locked"
                    type="button"
                    class="secondary-chip"
                    :disabled="operationBusy || disabled"
                    @click="checkResult"
                >
                    Check import outcome
                </button>
                <p v-if="run" class="text-xs text-sem-fg-muted">Import reference: {{ run.id }}</p>
            </div>
        </details>
    </section>
</template>
<script setup>
import { ref, computed, watch, onBeforeUnmount } from "vue";
import { apiPath } from "../../js/constants";
import DownloadUtils from "../../js/DownloadUtils";
import DialogUtils from "../../js/DialogUtils";
import { meshcoreBackupChoices } from "../../js/meshcoreSetupBackup";
const lifetime = new AbortController();
const props = defineProps({ snapshot: { type: Object, required: true }, disabled: Boolean, importOnly: Boolean });
const emit = defineEmits(["changed", "busy", "device-hint"]);
const backupPassword = ref(""),
    confirmation = ref(""),
    exporting = ref(false),
    backupError = ref(""),
    backupNotice = ref("");
const deviceChoices = ref([]),
    deviceIndex = ref(0),
    connectionHint = ref(null);
const fileName = ref("");
const raw = ref(""),
    encrypted = ref(false),
    importPassword = ref(""),
    working = ref(false),
    importError = ref(""),
    preview = ref(null),
    chosen = ref([]),
    result = ref(null),
    run = ref(null),
    locked = ref(false);
const uncertainImport = computed(
    () => run.value && locked.value && !["complete", "not_found"].includes(result.value?.state)
);
const operationBusy = computed(() => exporting.value || working.value);
watch(operationBusy, (value) => emit("busy", value));
let exportRevision = 0,
    reviewRevision = 0,
    disposed = false;
const passwordValid = computed(() => {
    const length = Array.from(backupPassword.value).length;
    return length >= 12 && length <= 1024 && backupPassword.value === confirmation.value;
});
function clearExport() {
    ++exportRevision;
    backupPassword.value = "";
    confirmation.value = "";
    backupError.value = "";
    backupNotice.value = "";
}
function backupToggled(event) {
    if (!event.target.open) clearExport();
}
function importToggled(event) {
    if (!event.target.open && !working.value) {
        ++reviewRevision;
        raw.value = "";
        deviceChoices.value = [];
        connectionHint.value = null;
        fileName.value = "";
        importPassword.value = "";
        preview.value = null;
        chosen.value = [];
    }
}
async function backup() {
    if (
        exporting.value ||
        working.value ||
        props.disabled ||
        !props.snapshot.connected ||
        !passwordValid.value ||
        !props.snapshot.owner
    )
        return;
    const owner = props.snapshot.owner,
        current = ++exportRevision;
    exporting.value = true;
    backupError.value = "";
    backupNotice.value = "";
    try {
        const { data } = await window.api.post(
            apiPath("/meshcore/backup"),
            { password: backupPassword.value, expected_public_key: owner },
            { timeout: 60000 }
        );
        if (disposed || current !== exportRevision || owner !== props.snapshot.owner) return;
        const value = data.result;
        const expected = ["format", "public_key", "salt", "nonce", "ciphertext", "tag"].sort();
        if (
            !value ||
            JSON.stringify(Object.keys(value).sort()) !== JSON.stringify(expected) ||
            value.format !== "meshchatnext-meshcore-identity-v1" ||
            value.public_key !== owner ||
            ![
                ["salt", 32],
                ["nonce", 24],
                ["ciphertext", 128],
                ["tag", 32],
            ].every(
                ([key, length]) =>
                    typeof value[key] === "string" && value[key].length === length && /^[0-9a-f]+$/i.test(value[key])
            )
        )
            throw new Error("Invalid encrypted backup");
        await DownloadUtils.downloadFile(
            `meshcore-identity-${owner.slice(0, 12)}.json`,
            new Blob([JSON.stringify(value, null, 2)], { type: "application/json" })
        );
        if (current === exportRevision)
            backupNotice.value = "Encrypted backup download requested. Complete file saving if prompted.";
    } catch (e) {
        if (!disposed && current === exportRevision)
            backupError.value =
                e?.response?.status === 409
                    ? "This radio firmware disables private-key export."
                    : "Could not prepare the encrypted backup. Check the connection and try again.";
    } finally {
        backupPassword.value = "";
        confirmation.value = "";
        exporting.value = false;
    }
}
async function loadFile(event) {
    if (operationBusy.value || props.disabled || uncertainImport.value) return;
    const file = event.target.files?.[0],
        current = ++reviewRevision;
    raw.value = "";
    deviceChoices.value = [];
    connectionHint.value = null;
    fileName.value = "";
    preview.value = null;
    chosen.value = [];
    result.value = null;
    run.value = null;
    locked.value = false;
    importPassword.value = "";
    importError.value = "";
    encrypted.value = false;
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) {
        importError.value = "Choose a JSON backup no larger than 2 MiB.";
        event.target.value = "";
        return;
    }
    try {
        const text = await file.text();
        if (disposed || current !== reviewRevision) return;
        const data = JSON.parse(text);
        if (!data || typeof data !== "object" || Array.isArray(data)) throw new Error("Invalid JSON");
        deviceChoices.value = meshcoreBackupChoices(data);
        deviceIndex.value = 0;
        // Preserve the original text for a single-device export, including strict backend validation.
        raw.value = Array.isArray(data.devices) ? JSON.stringify(deviceChoices.value[0].config) : text;
        connectionHint.value = deviceChoices.value[0].connection;
        emit("device-hint", connectionHint.value);
        fileName.value = file.name || "Selected JSON backup";
        encrypted.value = ["meshchatnext-meshcore-identity-v1", "meshchatx-meshcore-identity-v1"].includes(
            deviceChoices.value[0].config.format
        );
    } catch {
        if (current === reviewRevision) importError.value = "Could not read this JSON backup.";
    }
    event.target.value = "";
}
function selectDevice() {
    if (working.value || exporting.value || props.disabled || uncertainImport.value) return;
    ++reviewRevision;
    const selected = deviceChoices.value[deviceIndex.value];
    if (!selected) return;
    raw.value = JSON.stringify(selected.config);
    connectionHint.value = selected.connection;
    encrypted.value = ["meshchatnext-meshcore-identity-v1", "meshchatx-meshcore-identity-v1"].includes(
        selected.config.format
    );
    preview.value = null;
    chosen.value = [];
    result.value = null;
    run.value = null;
    locked.value = false;
    importPassword.value = "";
    emit("device-hint", connectionHint.value);
}
async function review() {
    if (working.value || exporting.value || props.disabled || !raw.value || !props.snapshot.connected) return;
    const current = ++reviewRevision,
        owner = props.snapshot.owner;
    working.value = true;
    importError.value = "";
    preview.value = null;
    chosen.value = [];
    result.value = null;
    locked.value = false;
    run.value = null;
    try {
        const { data } = await window.api.post(
            apiPath("/meshcore/config-preview"),
            { text: raw.value, ...(encrypted.value ? { password: importPassword.value } : {}) },
            { timeout: 120000 }
        );
        if (disposed || current !== reviewRevision || owner !== props.snapshot.owner) return;
        preview.value = data.result;
        if (props.importOnly) chosen.value = data.result.sections.filter((section) => !data.result.errors?.[section]);
    } catch {
        if (!disposed && current === reviewRevision)
            importError.value =
                "Could not validate this backup against the connected radio. Check the file, password and connection.";
    } finally {
        working.value = false;
    }
}
function sectionLabel(section) {
    const item = preview.value;
    if (section === "name") return `Radio name: ${item.name}`;
    if (section === "radio") {
        const labels = {
            frequency_mhz: ["Frequency", "MHz"],
            bandwidth_khz: ["Bandwidth", "kHz"],
            sf: ["SF", ""],
            cr: ["CR", ""],
            tx_power_dbm: ["TX", "dBm"],
        };
        return (
            "Radio settings: " +
            Object.entries(item.radio)
                .map(([key, value]) =>
                    `${labels[key]?.[0] || key} ${key === "cr" ? "4/" + value : value} ${labels[key]?.[1] || ""}`.trim()
                )
                .join(" · ")
        );
    }
    if (section === "identity")
        return item.identity_replacement
            ? "Identity · replace current identity"
            : "Identity · already matches this radio";
    if (section === "contacts") return `Contacts · ${item.contacts.new} new, ${item.contacts.existing} existing kept`;
    return `Channels · ${item.channels.new} new, ${item.channels.existing} existing kept, ${item.channels.free_slots} free slots`;
}
function unsupportedLabel(field) {
    return (
        {
            position_settings: "Position settings",
            other_settings: "Other radio preferences",
            auto_add_settings: "Automatic contact-add preferences",
            region_transport_keys: "Region transport keys",
            "contacts.out_path_list": "Cached contact routes (new contacts start with flood routing)",
            "contacts.custom_name": "App-specific contact aliases",
            "channels.message_retention_duration_seconds": "Per-channel message retention",
        }[field] || field
    );
}
async function apply() {
    if (
        working.value ||
        exporting.value ||
        props.disabled ||
        locked.value ||
        !preview.value ||
        !chosen.value.length ||
        !props.snapshot.connected ||
        preview.value.owner !== props.snapshot.owner
    )
        return;
    const replacement = chosen.value.includes("identity") && preview.value.identity_replacement;
    const confirmed = await DialogUtils.confirm(
        replacement
            ? "Replace the connected MeshCore radio identity with the backup identity and import the selected sections? This changes the private key on the radio."
            : "Import the selected MeshCore sections? Existing contacts and channels will be kept. Changes are applied in steps and cannot be rolled back automatically."
    );
    if (!confirmed || !preview.value || preview.value.owner !== props.snapshot.owner) return;
    run.value = { id: crypto.randomUUID(), owner: preview.value.owner };
    locked.value = true;
    working.value = true;
    importError.value = "";
    try {
        const { data } = await window.api.post(
            apiPath("/meshcore/config-apply"),
            {
                text: raw.value,
                sections: [...chosen.value],
                expected_owner: run.value.owner,
                preview_id: preview.value.preview_id,
                request_id: run.value.id,
                replace_identity: Boolean(replacement),
                ...(encrypted.value ? { password: importPassword.value } : {}),
            },
            { timeout: 600000 }
        );
        if (disposed) return;
        result.value = data.result;
        emit("changed", data.result);
    } catch {
        if (!disposed)
            importError.value =
                "The import outcome is unknown. Check its outcome and inspect the radio before making a new preview. Nothing will be retried automatically.";
    } finally {
        working.value = false;
        raw.value = "";
        importPassword.value = "";
    }
}
async function checkResult() {
    if (!run.value || working.value || exporting.value || props.disabled) return;
    working.value = true;
    importError.value = "";
    try {
        const { data } = await window.api.get(apiPath("/meshcore/config-result"), {
            signal: lifetime.signal,
            params: { owner: run.value.owner, request_id: run.value.id },
        });
        if (!disposed) {
            result.value = data.result;
            emit("changed", data.result);
        }
    } catch {
        if (!disposed) importError.value = "Could not read the import receipt. No changes were retried.";
    } finally {
        working.value = false;
    }
}
watch(
    [() => props.snapshot.owner, () => props.snapshot.connected],
    () => {
        clearExport();
        // In the first-launch importer the user may select the file before connecting.
        // Retain that explicit selection, but invalidate any old preview/receipt.
        if (props.importOnly && raw.value && !locked.value && !working.value) {
            ++reviewRevision;
            importPassword.value = "";
            preview.value = null;
            chosen.value = [];
            return;
        }
        if (!working.value) {
            ++reviewRevision;
            raw.value = "";
            importPassword.value = "";
            preview.value = null;
            chosen.value = [];
        }
    },
    { flush: "sync" }
);
onBeforeUnmount(() => {
    deviceChoices.value = [];
    connectionHint.value = null;
    lifetime.abort();
    disposed = true;
    emit("busy", false);
    clearExport();
    ++reviewRevision;
    raw.value = "";
    importPassword.value = "";
});
</script>
<style scoped>
@reference "../../style.css";
.input-field {
    @apply bg-sem-surface-muted border border-sem-border text-sm rounded-2xl focus:ring-2 focus:ring-sem-focus focus:border-sem-focus-border block w-full p-2.5 text-sem-fg transition;
}
button {
    @apply disabled:opacity-50 disabled:cursor-not-allowed;
}
</style>
