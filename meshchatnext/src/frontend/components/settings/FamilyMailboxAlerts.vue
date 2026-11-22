<!-- SPDX-License-Identifier: 0BSD -->
<template>
    <details class="rounded-xl border border-sem-border p-4">
        <summary class="cursor-pointer font-medium">{{ $t("mailbox_alerts.title") }}</summary>
        <div class="mt-4 space-y-3">
            <p class="text-sm text-sem-fg-muted">{{ $t("mailbox_alerts.intro") }}</p>
            <label class="block space-y-1">
                <span class="text-sm">{{ $t("mailbox_alerts.search") }}</span>
                <input
                    v-model="search"
                    class="input-field w-full"
                    type="search"
                    data-testid="mailbox-contact-search"
                    @input="searchContacts"
                />
            </label>
            <label class="block space-y-1">
                <span class="text-sm">{{ $t("mailbox_alerts.contact") }}</span>
                <select v-model="selected" class="input-field w-full" :disabled="busy" data-testid="mailbox-contact">
                    <option value="">{{ $t("mailbox_alerts.select_contact") }}</option>
                    <option v-for="contact in options" :key="contact.id" :value="String(contact.id)">
                        {{ contact.name }} · {{ contact.lxmf_address.slice(0, 8) }}…
                    </option>
                </select>
            </label>
            <button
                type="button"
                class="secondary-chip min-h-9"
                :disabled="loadingContacts || busy"
                data-testid="mailbox-refresh"
                @click="refresh"
            >
                {{ $t("mailbox_alerts.refresh") }}
            </button>
            <p v-if="!loadingContacts && !contacts.length" class="text-sm text-sem-fg-muted">
                {{ $t("mailbox_alerts.no_contacts") }}
            </p>
            <fieldset v-if="selected" :disabled="busy || !loaded" class="space-y-3">
                <p class="text-sm font-medium" data-testid="mailbox-route-state">
                    {{ $t(saved ? "mailbox_alerts.on" : "mailbox_alerts.off") }}
                </p>
                <label class="block space-y-1">
                    <span class="text-sm">{{ $t("mailbox_alerts.provider") }}</span>
                    <input
                        v-model="provider"
                        type="url"
                        maxlength="2048"
                        class="input-field w-full"
                        autocapitalize="none"
                        :spellcheck="false"
                        data-testid="mailbox-provider"
                    />
                </label>
                <label class="block space-y-1">
                    <span class="text-sm">{{ $t("mailbox_alerts.audience") }}</span>
                    <input
                        v-model="audience"
                        maxlength="128"
                        class="input-field w-full"
                        autocapitalize="none"
                        :spellcheck="false"
                        data-testid="mailbox-audience"
                    />
                </label>
                <label class="block space-y-1">
                    <span class="text-sm">{{ $t("mailbox_alerts.relay") }}</span>
                    <input
                        v-model="relay"
                        maxlength="32"
                        class="input-field w-full font-mono"
                        autocapitalize="none"
                        :spellcheck="false"
                        data-testid="mailbox-relay"
                    />
                </label>
                <p class="text-sm text-sem-fg-muted">{{ $t("mailbox_alerts.relay_help") }}</p>
                <p class="text-sm text-sem-fg-muted">{{ $t("mailbox_alerts.privacy") }}</p>
                <div class="flex flex-wrap gap-2">
                    <button
                        type="button"
                        class="secondary-chip min-h-10"
                        :disabled="!valid || busy || !loaded"
                        data-testid="mailbox-save"
                        @click="save"
                    >
                        {{ $t("mailbox_alerts.save") }}
                    </button>
                    <button
                        type="button"
                        class="secondary-chip min-h-10"
                        :disabled="!saved || busy || !loaded"
                        data-testid="mailbox-remove"
                        @click="remove"
                    >
                        {{ $t("mailbox_alerts.remove") }}
                    </button>
                </div>
            </fieldset>
            <p v-if="error" role="alert" class="text-sm text-sem-danger">{{ error }}</p>
            <p v-if="message" role="status" class="text-sm text-sem-fg-muted">{{ message }}</p>
        </div>
    </details>
</template>

<script setup>
import { computed, getCurrentInstance, onBeforeUnmount, ref, watch } from "vue";
import { apiPath } from "../../js/constants";

const props = defineProps({ visible: { type: Boolean, default: true }, preferredRelay: { type: String, default: "" } });
const instance = getCurrentInstance();
const t = (key) => instance.proxy.$t(key);
const contacts = ref([]),
    search = ref(""),
    selected = ref(""),
    selectedContact = ref(null);
const provider = ref(""),
    audience = ref(""),
    relay = ref(""),
    saved = ref(false),
    loaded = ref(false);
const busy = ref(false),
    loadingContacts = ref(false),
    error = ref(""),
    message = ref("");
const drafts = new Map();
const original = ref("");
let alive = true,
    contactsEpoch = 0,
    routeEpoch = 0,
    searchTimer;
const options = computed(() =>
    selectedContact.value && !contacts.value.some((row) => row.id === selectedContact.value.id)
        ? [selectedContact.value, ...contacts.value]
        : contacts.value
);
const valid = computed(() => {
    try {
        const url = new URL(provider.value.trim());
        return (
            url.protocol === "https:" &&
            Boolean(url.hostname) &&
            !url.username &&
            !url.password &&
            url.pathname === "/" &&
            !url.search &&
            !url.hash &&
            audience.value.trim().length > 0 &&
            audience.value.trim().length <= 128 &&
            /^[a-f0-9]{32}$/i.test(relay.value.trim())
        );
    } catch {
        return false;
    }
});
function draft() {
    const value = { provider: provider.value, audience: audience.value, relay: relay.value };
    return { ...value, dirty: JSON.stringify(value) !== original.value };
}
function assign(value) {
    provider.value = value?.provider || "";
    audience.value = value?.audience || "";
    relay.value = value?.relay || props.preferredRelay || "";
}
async function loadContacts() {
    const epoch = ++contactsEpoch;
    loadingContacts.value = true;
    try {
        const response = await window.api.get(apiPath("/telephone/contacts"), {
            params: { limit: 500, search: search.value.trim() || undefined },
        });
        if (alive && epoch === contactsEpoch)
            contacts.value = (response.data.contacts || []).filter(
                (row) =>
                    Number.isSafeInteger(row.id) &&
                    typeof row.lxmf_address === "string" &&
                    /^[a-f0-9]{32}$/i.test(row.lxmf_address)
            );
    } catch {
        if (alive && epoch === contactsEpoch) error.value = t("mailbox_alerts.load_failed");
    } finally {
        if (alive && epoch === contactsEpoch) loadingContacts.value = false;
    }
}
function searchContacts() {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(loadContacts, 250);
}
watch(
    () => props.visible,
    (value) => {
        if (value && (!contactsEpoch || !contacts.value.length)) void loadContacts();
    },
    { immediate: true }
);
async function loadRoute(id, old) {
    const epoch = ++routeEpoch;
    if (old && loaded.value) {
        const value = draft();
        if (value.dirty) drafts.set(old, value);
        else drafts.delete(old);
    }
    selectedContact.value = options.value.find((row) => String(row.id) === id) || null;
    loaded.value = false;
    saved.value = false;
    error.value = "";
    message.value = "";
    assign(null);
    if (!id) return;
    const pending = drafts.get(id);
    if (pending) assign(pending);
    try {
        const response = await window.api.get(apiPath(`/telephone/contacts/${id}/mailbox-alert-route`));
        if (!alive || epoch !== routeEpoch) return;
        const remote = {
            provider: response.data.route?.provider || "",
            audience: response.data.route?.audience || "",
            relay: response.data.route?.relay || props.preferredRelay || "",
        };
        if (!pending) assign(remote);
        original.value = JSON.stringify(remote);
        saved.value = Boolean(response.data.route);
        loaded.value = true;
    } catch {
        if (alive && epoch === routeEpoch) error.value = t("mailbox_alerts.load_failed");
    }
}
watch(selected, loadRoute);
async function refresh() {
    error.value = "";
    await loadContacts();
    if (selected.value) await loadRoute(selected.value, selected.value);
}

async function update(removeRoute) {
    if (!selected.value || !loaded.value || busy.value || (!removeRoute && !valid.value)) return;
    busy.value = true;
    error.value = "";
    message.value = "";
    const epoch = routeEpoch;
    const url = apiPath(`/telephone/contacts/${selected.value}/mailbox-alert-route`);
    try {
        const response = removeRoute
            ? await window.api.delete(url)
            : await window.api.post(url, {
                  route: {
                      provider: provider.value.trim().replace(/\/$/, ""),
                      audience: audience.value.trim(),
                      relay: relay.value.trim().toLowerCase(),
                  },
              });
        if (!alive || epoch !== routeEpoch) return;
        assign(response.data.route);
        saved.value = Boolean(response.data.route);
        original.value = JSON.stringify({ provider: provider.value, audience: audience.value, relay: relay.value });
        drafts.delete(selected.value);
        message.value = t(removeRoute ? "mailbox_alerts.removed" : "mailbox_alerts.saved");
    } catch {
        if (alive && epoch === routeEpoch) error.value = t("mailbox_alerts.save_failed");
    } finally {
        if (alive && epoch === routeEpoch) busy.value = false;
    }
}
function save() {
    return update(false);
}
function remove() {
    return update(true);
}
onBeforeUnmount(() => {
    alive = false;
    ++contactsEpoch;
    ++routeEpoch;
    clearTimeout(searchTimer);
});
</script>
