<template>
    <details class="px-4 py-2 border-b border-sem-border text-sm" data-private-location>
        <summary class="cursor-pointer font-semibold">Private location</summary>
        <div class="space-y-3 pt-3 pb-2">
            <p class="text-xs text-sem-fg-muted">
                Family-compatible encrypted direct messages. These controls are separate from saving a contact. Sharing
                is one-time; rooms and channels are never selected here.
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
                Allow one-time location sharing with this contact
            </label>
            <button
                type="button"
                class="secondary-chip"
                data-private-location-share
                :disabled="loading || sharing || !connected || !known || !policy.share"
                @click="shareOnce"
            >
                {{ sharing ? "Getting or submitting location…" : "Share my location once" }}
            </button>
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
import { ref, watch, onBeforeUnmount } from "vue";
import { apiPath } from "../../js/constants";
import { getAndroidPosition, isAndroidLocationSupported } from "../../js/androidLocation";
const props = defineProps({
    owner: { type: String, required: true },
    peer: { type: String, required: true },
    radioId: { type: String, default: null },
    contextKey: { type: String, default: null },
    connected: { type: Boolean, default: false },
});
const policy = ref({ receive: false, share: false, generation: null });
const known = ref(false);
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
function shareOnce() {
    if (
        loading.value ||
        sharing.value ||
        !props.connected ||
        !known.value ||
        !policy.value.share ||
        !policy.value.generation
    )
        return;
    const token = epoch,
        c = context(),
        generation = policy.value.generation;
    const nativeLocation = isAndroidLocationSupported();
    if (!nativeLocation && !navigator.geolocation) {
        notice.value = "Location is unavailable on this device.";
        return;
    }
    sharing.value = true;
    notice.value = "";
    let completed = false;
    const unavailable = () => {
        if (completed) return;
        completed = true;
        if (current(c, token)) {
            sharing.value = false;
            notice.value = "Location was unavailable or permission was declined. Nothing was shared.";
        }
    };
    const submit = async (position) => {
        if (completed) return;
        completed = true;
        if (!current(c, token) || !policy.value.share || generation !== policy.value.generation) return;
        const coords = position.coords;
        const fix = {
            latitude: coords.latitude,
            longitude: coords.longitude,
            altitude: coords.altitude ?? 0,
            accuracy: coords.accuracy,
            speed: coords.speed ?? 0,
            bearing: coords.heading ?? 0,
            last_update: Math.floor(position.timestamp / 1000),
        };
        try {
            const result = await request("send", { fix, generation, request_id: crypto.randomUUID() }, c);
            if (current(c, token)) {
                if (result.state !== "accepted") known.value = false;
                notice.value =
                    result.state === "accepted"
                        ? "Accepted by the selected radio. Delivery is not yet confirmed."
                        : result.state === "rejected"
                          ? "Location was not sent."
                          : "The result is uncertain. No automatic retry was made.";
            }
        } catch (error) {
            if (current(c, token)) {
                known.value = false;
                notice.value =
                    error?.response?.data?.message || "Could not confirm sharing. No automatic retry was made.";
            }
        } finally {
            if (epoch === token) sharing.value = false;
        }
    };
    try {
        if (nativeLocation) {
            getAndroidPosition().then(
                (pos) =>
                    submit({
                        coords: {
                            latitude: pos.latitude,
                            longitude: pos.longitude,
                            altitude: pos.altitude,
                            accuracy: pos.accuracy,
                            speed: pos.speed,
                            heading: pos.bearing,
                        },
                        timestamp: pos.time,
                    }),
                unavailable
            );
        } else {
            navigator.geolocation.getCurrentPosition(submit, unavailable, {
                enableHighAccuracy: true,
                maximumAge: 0,
                timeout: 15000,
            });
        }
    } catch {
        unavailable();
    }
}

watch(() => [props.owner, props.peer, props.radioId, props.contextKey, props.connected], load, { immediate: true });
onBeforeUnmount(() => {
    stopped = true;
    epoch++;
});
</script>
