<template>
    <details class="px-4 py-2 border-b border-sem-border text-sm" data-private-location>
        <summary class="cursor-pointer font-semibold">Share my location</summary>
        <div class="space-y-3 pt-3 pb-2">
            <p class="text-xs text-sem-fg-muted">
                Send your current location privately to {{ name }}. If they allow location sharing, it will appear on
                their map.
            </p>
            <label class="flex items-start gap-2">
                <input
                    type="checkbox"
                    :checked="policy.receive"
                    :disabled="loading || !known"
                    @change="configure('receive', $event)"
                />
                Show this contact’s private locations on my map
            </label>
            <label class="flex items-start gap-2">
                <input
                    type="checkbox"
                    :checked="policy.share"
                    :disabled="loading || !known"
                    @change="configure('share', $event)"
                />
                Allow private location sharing with this contact
            </label>
            <div v-if="timedActive" class="flex flex-wrap items-center gap-2">
                <span class="text-xs" role="status">Sharing location</span>
                <button type="button" class="secondary-chip" @click="session?.stop()">Stop sharing</button>
            </div>
            <div v-else class="flex flex-wrap items-center gap-2">
                <select
                    v-model.number="minutes"
                    class="input-field text-xs"
                    aria-label="Location sharing duration"
                    :disabled="loading || sharing || !connected || !known || !policy.share"
                >
                    <option :value="0">One time</option>
                    <option :value="15">15 minutes</option>
                    <option :value="60">60 minutes</option>
                </select>
                <button
                    type="button"
                    class="secondary-chip"
                    data-private-location-share
                    :disabled="loading || sharing || !connected || !known || !policy.share"
                    @click="shareLocation"
                >
                    {{
                        sharing
                            ? "Getting or submitting location…"
                            : minutes
                              ? "Start sharing"
                              : "Share my location once"
                    }}
                </button>
            </div>
            <p class="text-xs text-sem-fg-muted">
                Received locations appear in the MeshCore map layer. Your device will ask for location permission.
                Already sent locations cannot be recalled.
            </p>
            <button v-if="!known && !loading" type="button" class="secondary-chip" @click="load">
                Try reading permissions again
            </button>
            <p v-if="notice" role="status" class="text-xs">{{ notice }}</p>
        </div>
    </details>
</template>
<script setup>
import { computed, ref, watch, onBeforeUnmount, onDeactivated, onActivated } from "vue";
import DialogUtils from "../../js/DialogUtils";
import {
    privateLocationSessions,
    readPrivateLocation,
    startPrivateLocationSession,
} from "../../js/timedPrivateLocation";
import { apiPath } from "../../js/constants";
import { isAndroidLocationSupported } from "../../js/androidLocation";
const props = defineProps({
    owner: { type: String, required: true },
    peer: { type: String, required: true },
    name: { type: String, default: "this contact" },
    radioId: { type: String, default: null },
    contextKey: { type: String, default: null },
    connected: { type: Boolean, default: false },
});
const policy = ref({ receive: false, share: false, generation: null });
const known = ref(false);
const minutes = ref(0);
const sessionKey = computed(() => `meshcore:${props.owner}:${props.peer}`);
const session = computed(() => privateLocationSessions.get(sessionKey.value));
const timedActive = computed(() => Boolean(session.value));
const loading = ref(false),
    sharing = ref(false),
    notice = ref("");
let epoch = 0,
    stopped = false;
function context() {
    return { owner: props.owner, peer: props.peer, radio: props.radioId, route: props.contextKey };
}
function sameContext(c, token) {
    return (
        !stopped &&
        epoch === token &&
        c.owner === props.owner &&
        c.peer === props.peer &&
        c.radio === props.radioId &&
        c.route === props.contextKey
    );
}
function current(c, token) {
    return props.connected && sameContext(c, token);
}

async function request(action, fields, c) {
    const { data } = await window.api.post(
        apiPath(`/meshcore/private-location-${action}`),
        { ...fields, peer: c.peer, expected_owner: c.owner },
        { params: { ...(c.radio ? { radio: c.radio } : {}) } }
    );
    return data.result;
}
async function load() {
    const token = ++epoch,
        c = context();
    minutes.value = 0;
    policy.value = { receive: false, share: false, generation: null };
    known.value = false;
    sharing.value = false;
    notice.value = "";
    loading.value = false;
    if (!props.owner) return;
    loading.value = true;
    try {
        const result = await request("status", {}, c);
        if (sameContext(c, token)) {
            policy.value = result;
            known.value = true;
        }
    } catch {
        if (sameContext(c, token)) notice.value = "Could not read private location permissions.";
    } finally {
        if (epoch === token) loading.value = false;
    }
}
async function configure(field, event) {
    session.value?.stop();
    const value = event.target.checked;
    const token = ++epoch,
        c = context();
    sharing.value = false;
    loading.value = true;
    notice.value = "";
    const desired = {
        receive: policy.value.receive,
        share: policy.value.share,
        generation: policy.value.generation,
        [field]: value,
    };
    try {
        const result = await request("configure", desired, c);
        if (sameContext(c, token)) {
            policy.value = result;
            known.value = true;
        }
    } catch {
        if (sameContext(c, token)) {
            known.value = false;
            notice.value = "Could not save private location permissions. Read them again before sharing.";
        }
    } finally {
        if (epoch === token) {
            loading.value = false;
            event.target.checked = Boolean(policy.value[field]);
        }
    }
}
async function shareLocation() {
    if (
        loading.value ||
        sharing.value ||
        timedActive.value ||
        !props.connected ||
        !known.value ||
        !policy.value.share ||
        !policy.value.generation
    )
        return;

    const token = epoch;
    const c = context();
    const generation = policy.value.generation;
    const duration = minutes.value;
    const key = sessionKey.value;
    const name = props.name;
    const source = isAndroidLocationSupported() ? "android" : "browser";
    const getFix = () => readPrivateLocation(source, undefined, 15000);
    const stillAllowed = () => current(c, token) && policy.value.share && generation === policy.value.generation;
    const sendFix = async (position) => {
        const fix = {
            latitude: position.latitude,
            longitude: position.longitude,
            altitude: position.altitude ?? 0,
            accuracy: position.accuracy,
            speed: position.speed ?? 0,
            bearing: position.bearing ?? 0,
            last_update: Math.floor((position.time || Date.now()) / 1000),
        };
        const result = await request("send", { fix, generation, request_id: crypto.randomUUID() }, c);
        if (result.state !== "accepted") {
            const error = new Error(
                result.state === "rejected"
                    ? "Location was not sent."
                    : "The result is uncertain. No automatic retry was made."
            );
            error.privateLocationRejected = true;
            throw error;
        }
    };

    sharing.value = true;
    notice.value = "";
    let acquiredFix = false;
    try {
        if (
            duration &&
            !(await DialogUtils.confirm(
                `Share your location privately with ${props.name} for up to ${duration} minutes? Sharing continues as you use neXt and stops if you put the app in the background.`
            ))
        )
            return;
        if (!stillAllowed()) return;

        const deadline = Date.now() + duration * 60_000;
        const firstFix = await getFix();
        acquiredFix = true;
        if (!stillAllowed() || document.hidden) return;
        await sendFix(firstFix);
        if (!stillAllowed()) return;

        notice.value = "Accepted by the selected radio. Delivery is not yet confirmed.";
        if (duration && !document.hidden) {
            // The backend verifies the original radio, owner and permission
            // generation on every send, even after this chat closes.
            startPrivateLocationSession(key, name, {
                deadline,
                firstFix,
                getFix,
                sendFix,
                isCurrent: () => true,
            });
        }
    } catch (error) {
        if (stillAllowed()) {
            if (acquiredFix) known.value = false;
            notice.value = acquiredFix
                ? error?.response?.data?.message ||
                  (error?.privateLocationRejected
                      ? error.message
                      : "Could not share this location. No automatic retry was made.")
                : "Location was unavailable or permission was declined. Nothing was shared.";
        }
    } finally {
        if (epoch === token) sharing.value = false;
    }
}

watch(() => [props.owner, props.peer, props.radioId, props.contextKey, props.connected], load, { immediate: true });
onActivated(() => {
    if (!known.value && !loading.value) load();
});
onDeactivated(() => {
    // Ignore a pending GPS result after leaving a cached conversation.
    epoch++;
    sharing.value = false;
    loading.value = false;
});
onBeforeUnmount(() => {
    stopped = true;
    epoch++;
});
</script>
