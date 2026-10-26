<template>
    <details class="border-t border-sem-border pt-2" aria-label="MeshCore team controls">
        <summary class="cursor-pointer font-semibold text-sm">Team · MeshCore / Open TAK</summary>
        <div class="space-y-2 mt-2 text-xs">
            <p>
                Use the same private channel in compatible Open TAK clients. Team aliases are shared-channel
                identifiers, not verified contacts.
            </p>
            <p>Position sharing is off until you choose a sharing action.</p>
            <details :open="!team?.enabled" class="border border-sem-border rounded-lg p-2">
                <summary class="cursor-pointer font-semibold">Team settings</summary>
                <div class="space-y-2 mt-2">
                    <label class="flex gap-2 items-center"
                        ><input v-model="draft.enabled" type="checkbox" /> Enable team mode</label
                    >
                    <label class="flex gap-2 items-center">
                        <input v-model="draft.monitor_geofences" type="checkbox" /> Monitor team geofences on this
                        device
                    </label>
                    <label class="flex gap-2 items-center">
                        <input v-model="draft.notify_team_alerts" type="checkbox" /> Notify on incoming team alerts
                    </label>
                    <p>
                        Team alerts use this separate switch rather than channel chat mute settings. Do not disturb
                        still applies.
                    </p>
                    <p>
                        Local alerts from received team positions only; no GPS or automatic transmissions. First
                        observations and gaps over 10 minutes establish a new baseline. Positions near the boundary are
                        ignored within their reported accuracy or 10 metres. Channel mute settings apply to chat
                        messages; this separate monitoring option controls boundary alerts. Team positions and crossing
                        reports are unverified.
                    </p>
                    <label class="block"
                        >Private team channel
                        <select v-model="draft.channel_id" class="input-field w-full" :disabled="working">
                            <option value="">Choose a private channel</option>
                            <option
                                v-for="channel in privateChannels"
                                :key="channel.channel_id"
                                :value="channel.channel_id"
                            >
                                {{ channel.name || "Private channel" }}
                            </option>
                        </select>
                    </label>
                    <label class="block"
                        >Callsign · up to 20 UTF-8 bytes<input
                            v-model="draft.callsign"
                            class="input-field w-full"
                            maxlength="20"
                    /></label>
                    <div class="grid grid-cols-2 gap-2">
                        <label
                            >Role<select v-model.number="draft.role" class="input-field w-full">
                                <option v-for="(role, i) in team?.roles || []" :key="i" :value="i">{{ role }}</option>
                            </select></label
                        >
                        <label
                            >Status<select v-model.number="draft.status" class="input-field w-full">
                                <option v-for="(status, i) in team?.statuses || []" :key="i" :value="i">
                                    {{ status || "Unspecified" }}
                                </option>
                            </select></label
                        >
                    </div>
                    <label class="block"
                        >Team colour<select v-model.number="draft.color" class="input-field w-full">
                            <option v-for="(color, i) in team?.colors || []" :key="i" :value="i">
                                {{ colorNames[i] || color }}
                            </option>
                        </select></label
                    >
                    <button
                        type="button"
                        class="secondary-chip"
                        :disabled="working || !connected || !supported"
                        @click="configure"
                    >
                        Save team settings
                    </button>
                </div>
            </details>
            <p v-if="!supported">Connect a companion with channel-data support to change team settings.</p>
            <template v-if="team?.enabled">
                <p class="font-semibold">Sharing to {{ selectedChannelName }} · MeshCore</p>
                <p>Channel scope: {{ activeScope === "*" ? "Unscoped" : activeScope || "Radio default" }}</p>
                <button type="button" class="secondary-chip" :disabled="!canSend" @click="sharePosition">
                    Share my position once
                </button>
                <p>
                    Requests this phone’s location only when pressed. Position updates are limited to one every 30
                    seconds.
                </p>
                <details class="border border-sem-border rounded-lg p-2">
                    <summary class="cursor-pointer">Share a tactical pin</summary>
                    <div class="space-y-2 mt-2">
                        <label class="block"
                            >Pin type<select v-model.number="pin.pin_kind" class="input-field w-full">
                                <option v-for="(kind, i) in team.pin_kinds" :key="i" :value="i">{{ kind }}</option>
                            </select></label
                        >
                        <label class="block"
                            >Label · 32 bytes<input v-model="pin.label" class="input-field w-full" maxlength="32"
                        /></label>
                        <label class="block"
                            >Note · 60 bytes<input v-model="pin.note" class="input-field w-full" maxlength="60"
                        /></label>
                        <label class="block"
                            >Latitude<input
                                v-model.number="pin.latitude"
                                type="number"
                                min="-90"
                                max="90"
                                step="any"
                                class="input-field w-full"
                        /></label>
                        <label class="block"
                            >Longitude<input
                                v-model.number="pin.longitude"
                                type="number"
                                min="-180"
                                max="180"
                                step="any"
                                class="input-field w-full"
                        /></label>
                        <MeshCoreTeamAttachment
                            :key="owner + team.channel_id + activeScope"
                            :owner="owner"
                            :channel-id="team.channel_id"
                            :connected="connected"
                            composer
                            @prepared="pin.attachment = $event"
                        />
                        <p v-if="pin.attachment">
                            {{
                                pin.attachment.mode === 40
                                    ? "Photo attached"
                                    : `Recording attached · ${pin.attachment.extra} seconds`
                            }}
                        </p>
                        <button type="button" class="secondary-chip" @click="centerPin">Use map centre</button>
                        <button type="button" class="secondary-chip" :disabled="!canSend" @click="sendPin">
                            Share pin
                        </button>
                    </div>
                </details>
                <MeshCoreTeamShapeForm
                    :key="owner + ':shapes'"
                    :owner="owner"
                    :team="team"
                    :source="drawSource"
                    :can-send="canSend"
                    @send="sendReport"
                />
                <MeshCoreCasevacForm
                    :key="owner + ':casevac'"
                    :team="team"
                    :map="map"
                    :can-send="canSend"
                    @send="sendReport"
                />
                <MeshCoreTeamReportForm
                    :key="owner + team.channel_id + activeScope"
                    :owner="owner"
                    :connected="connected"
                    :team="team"
                    :map="map"
                    :can-send="canSend"
                    @send="sendReport"
                />
                <details class="border border-sem-border rounded-lg p-2">
                    <summary class="cursor-pointer">Team alert</summary>
                    <div class="space-y-2 mt-2">
                        <select v-model.number="alertKind" aria-label="Team alert type" class="input-field w-full">
                            <option v-for="(kind, i) in team.alert_kinds" :key="i" :value="i">{{ kind }}</option>
                        </select>
                        <input
                            v-model="alertNote"
                            aria-label="Team alert note"
                            class="input-field w-full"
                            maxlength="80"
                            placeholder="Note · 80 bytes"
                        />
                        <label class="flex gap-2 items-center"
                            ><input v-model="alertLocation" type="checkbox" /> Include map-centre location</label
                        >
                        <p v-if="!alertLocation">No location will be included.</p>
                        <p>Shared with your team channel only. This does not contact emergency services.</p>
                        <button type="button" class="secondary-chip" :disabled="!canSend" @click="sendAlert">
                            Send team alert…
                        </button>
                    </div>
                </details>
                <ul class="space-y-1" aria-label="MeshCore team items">
                    <li
                        v-for="item in activeItems"
                        :key="item.kind + item.alias + (item.id ?? '')"
                        class="border border-sem-border rounded-lg p-2"
                    >
                        <button type="button" class="text-left w-full" @click="$emit('focus', item)">
                            <span class="font-semibold">{{ item.label || item.callsign || item.alias }}</span> ·
                            {{ item.kind }}
                            <span v-if="item.kind === 'alert'">
                                · {{ team.alert_kinds[item.alert_kind] || "Alert" }}</span
                            >
                            <span class="block text-sem-fg-muted"
                                >MeshCore team · {{ item.alias }} · {{ age(item.heard)
                                }}<span v-if="item.kind === 'position' && Date.now() / 1000 - item.heard >= 600">
                                    · stale position</span
                                ></span
                            >
                            <span v-if="item.kind === 'shape'" class="block"
                                >{{ team.shape_kinds?.[item.shape_kind] || "Drawing" }} ·
                                {{ item.points?.length || 0 }} vertices<span v-if="item.geofence">
                                    · {{ team.geofences?.[item.geofence] }} geofence ·
                                    {{ team.monitor_geofences ? "monitoring on" : "monitoring off" }}</span
                                ></span
                            >
                            <span v-if="item.kind === 'casevac'" class="block"
                                ><span v-for="line in casevacLines(item)" :key="line" class="block">{{ line }}</span
                                >{{ item.remarks }}</span
                            >
                            <span v-if="item.note" class="block">{{ item.note }}</span>
                            <span v-if="item.kind === 'report'" class="block"
                                >{{ team.urgencies?.[item.urgency] }} · {{ item.place }}<br />{{ item.activity
                                }}<br v-if="item.unit || item.equipment" />{{ item.unit }} {{ item.equipment }}</span
                            >
                        </button>
                        <MeshCoreTeamAttachment
                            v-if="item.attachment"
                            :owner="owner"
                            :channel-id="team.channel_id"
                            :connected="connected"
                            :item="item"
                            :contacts="contacts"
                        />
                        <button
                            v-if="item.alias === team.alias && item.kind !== 'position'"
                            type="button"
                            class="secondary-chip mt-1"
                            :disabled="!canSend"
                            @click="remove(item)"
                        >
                            {{
                                item.kind === "alert"
                                    ? "Clear alert"
                                    : item.kind === "shape"
                                      ? "Remove drawing"
                                      : ["report", "casevac"].includes(item.kind)
                                        ? "Withdraw report"
                                        : "Remove pin"
                            }}
                        </button>
                    </li>
                </ul>
            </template>
            <MeshCoreCotServer
                :owner="owner"
                :team="team"
                :scope="activeScope"
                :connected="connected"
                @package="serverPackage = $event"
                @refresh="$emit('refresh')"
                @focus="$emit('focus', $event)"
            />
            <MeshCoreBeaconControls :owner="owner" :team="team" :scope="activeScope" :connected="connected" />
            <MeshCoreTakExchange
                :incoming-package="serverPackage"
                :contacts="contacts"
                :owner="owner"
                :team="team"
                :scope="activeScope"
                :connected="connected"
                :supported="supported"
                @refresh="$emit('refresh')"
                @focus="$emit('focus', $event)"
            />
            <p v-if="working" role="status">{{ locating ? "Getting phone location…" : "Working…" }}</p>
            <p v-if="notice" role="status">{{ notice }}</p>
            <p v-if="problem" role="alert" class="text-sem-danger">{{ problem }}</p>
        </div>
    </details>
</template>
<script setup>
/* eslint-disable security/detect-possible-timing-attacks -- Public radio IDs and lifetime counters are not secrets. */
import MeshCoreCotServer from "./MeshCoreCotServer.vue";
import MeshCoreBeaconControls from "./MeshCoreBeaconControls.vue";
import MeshCoreTakExchange from "./MeshCoreTakExchange.vue";
import { ref, computed, watch, onBeforeUnmount } from "vue";
import { toLonLat } from "ol/proj";
import { getAndroidPosition, isAndroidLocationSupported } from "../../../js/androidLocation";
import { apiPath } from "../../../js/constants";
import MeshCoreTeamShapeForm from "./MeshCoreTeamShapeForm.vue";
import MeshCoreCasevacForm from "./MeshCoreCasevacForm.vue";
import { casevacLines } from "../../../js/meshcoreCasevac";
import MeshCoreTeamAttachment from "./MeshCoreTeamAttachment.vue";
import MeshCoreTeamReportForm from "./MeshCoreTeamReportForm.vue";
import DialogUtils from "../../../js/DialogUtils";
const props = defineProps({
    owner: { type: String, default: null },
    team: { type: Object, default: null },
    channels: { type: Array, default: () => [] },
    contacts: { type: Array, default: () => [] },
    defaultScope: { type: String, default: null },
    connected: Boolean,
    supported: Boolean,
    map: { type: Object, default: null },
    drawSource: { type: Object, default: null },
});
const emit = defineEmits(["refresh", "focus"]);
const serverPackage = ref(null);
const defaults = () => ({
    enabled: false,
    monitor_geofences: false,
    notify_team_alerts: false,
    channel_id: "",
    callsign: "",
    role: 0,
    color: 0,
    status: 0,
});
const draft = ref(defaults()),
    working = ref(false),
    locating = ref(false),
    problem = ref(""),
    notice = ref("");
const pin = ref({ latitude: "", longitude: "", label: "", note: "", pin_kind: 0 });
const colorNames = [
    "Cyan",
    "White",
    "Yellow",
    "Orange",
    "Magenta",
    "Red",
    "Maroon",
    "Purple",
    "Dark blue",
    "Blue",
    "Teal",
    "Green",
    "Dark green",
    "Brown",
];
const alertKind = ref(4),
    alertNote = ref(""),
    alertLocation = ref(false);
let generation = 0;
const privateChannels = computed(() => props.channels.filter((c) => c.kind === "private"));
const selectedChannelName = computed(
    () => props.channels.find((c) => c.channel_id === props.team?.channel_id)?.name || "private team channel"
);
const activeScope = computed(
    () => props.channels.find((c) => c.channel_id === props.team?.channel_id)?.scope ?? props.defaultScope ?? null
);
watch(activeScope, () => {
    delete pin.value.attachment;
    generation++;
    working.value = false;
    locating.value = false;
    notice.value = "";
});
const canSend = computed(() => !working.value && props.connected && props.supported && props.team?.enabled);
const activeItems = computed(() =>
    (props.team?.records || []).filter((r) => !r.deleted && !r.withdrawn && (r.kind !== "alert" || r.active))
);
// Polling must not overwrite unsaved form edits.
watch(
    [() => props.owner, () => props.team?.channel_id],
    () => {
        generation++;
        serverPackage.value = null;
        draft.value = { ...defaults(), ...config(props.team) };
        working.value = false;
        locating.value = false;
        problem.value = "";
        notice.value = "";
        pin.value = { latitude: "", longitude: "", label: "", note: "", pin_kind: 0 };
        alertNote.value = "";
        alertLocation.value = false;
    },
    { immediate: true }
);
function config(team) {
    return Object.fromEntries(Object.keys(defaults()).map((k) => [k, team?.[k] ?? defaults()[k]]));
}
function age(time) {
    const m = Math.max(0, Math.floor((Date.now() / 1000 - time) / 60));
    return m < 1 ? "just heard" : `${m} minutes ago`;
}
async function action(endpoint, body, token, owner) {
    const { data } = await window.api.post(apiPath(`/meshcore/${endpoint}`), { ...body, expected_owner: owner });
    if (token !== generation) return;
    const result = data.result || {};
    notice.value =
        endpoint === "team-configure"
            ? "Team settings saved. No position was sent."
            : result.state === "submitted"
              ? "Submitted to the MeshCore radio. Channel delivery is not acknowledged."
              : result.state === "rejected"
                ? "Radio rejected this update."
                : "Transmission could not be confirmed. It will not be retried automatically.";
    emit("refresh");
}
async function run(task) {
    if (working.value || !props.connected || !props.supported) return;
    const token = generation,
        owner = props.owner;
    working.value = true;
    problem.value = "";
    notice.value = "";
    try {
        await task(token, owner);
    } catch (error) {
        if (token === generation)
            problem.value =
                error?.response?.data?.error || error?.message || "Team action failed. Refresh before trying again.";
    } finally {
        if (token === generation) {
            working.value = false;
            locating.value = false;
        }
    }
}
function configure() {
    return run((token, owner) => action("team-configure", { ...draft.value }, token, owner));
}
function send(record, token, owner) {
    return action(
        "team-send",
        {
            record,
            request_id: crypto.randomUUID(),
            expected_channel_id: props.team?.channel_id,
            expected_scope: activeScope.value,
        },
        token,
        owner
    );
}
function sharePosition() {
    if (!canSend.value) return;
    return run(async (token, owner) => {
        locating.value = true;
        let position;
        if (isAndroidLocationSupported()) position = { coords: await getAndroidPosition() };
        else {
            if (!navigator.geolocation) throw new Error("Phone location is unavailable.");
            position = await new Promise((resolve, reject) =>
                navigator.geolocation.getCurrentPosition(resolve, reject, {
                    enableHighAccuracy: true,
                    timeout: 20000,
                    maximumAge: 0,
                })
            );
        }
        if (token !== generation) return;
        locating.value = false;
        const c = position.coords;
        await send(
            {
                kind: "position",
                latitude: c.latitude,
                longitude: c.longitude,
                accuracy: Math.min(255, Math.max(0, Math.round(c.accuracy || 0))),
            },
            token,
            owner
        );
    });
}
function centerPin() {
    const center = props.map?.getView?.().getCenter();
    if (center) {
        const [lon, lat] = toLonLat(center);
        pin.value.longitude = +lon.toFixed(7);
        pin.value.latitude = +lat.toFixed(7);
    }
}
function sendPin() {
    if (canSend.value) return run((token, owner) => send({ kind: "pin", ...pin.value }, token, owner));
}
function sendAlert() {
    if (!canSend.value) return;
    return run(async (token, owner) => {
        const location = {};
        if (alertLocation.value) {
            const center = props.map?.getView?.().getCenter();
            if (!center) throw new Error("Map centre is unavailable.");
            const [longitude, latitude] = toLonLat(center);
            if (
                !Number.isFinite(latitude) ||
                !Number.isFinite(longitude) ||
                Math.abs(latitude) > 90 ||
                Math.abs(longitude) > 180
            )
                throw new Error("Choose a valid map centre before sending.");
            Object.assign(location, { latitude, longitude });
        }
        if (
            await DialogUtils.confirm(
                `Send ${props.team.alert_kinds[alertKind.value]} to ${selectedChannelName.value}? ${alertLocation.value ? `Map location: ${location.latitude.toFixed(5)}, ${location.longitude.toFixed(5)}.` : "No location included."}`,
                "MeshCore team alert"
            )
        ) {
            if (token === generation)
                await send(
                    { kind: "alert", active: true, alert_kind: alertKind.value, note: alertNote.value, ...location },
                    token,
                    owner
                );
        }
    });
}
function sendReport(record) {
    if (canSend.value) return run((token, owner) => send(record, token, owner));
}
function remove(item) {
    if (!canSend.value) return;
    let record;
    if (item.kind === "pin")
        record = {
            kind: "pin",
            id: item.id,
            latitude: item.latitude,
            longitude: item.longitude,
            deleted: true,
            label: item.label || "",
            note: "",
            pin_kind: item.pin_kind,
        };
    else if (item.kind === "shape") {
        record = Object.fromEntries(
            ["kind", "id", "shape_kind", "color", "label", "geofence", "radius_m", "route_method"].map((k) => [
                k,
                item[k],
            ])
        );
        record.deleted = true;
        record.points = [];
    } else if (item.kind === "casevac") {
        record = { kind: "casevac", id: item.id, latitude: item.latitude, longitude: item.longitude, deleted: true };
    } else if (item.kind === "report") {
        record = Object.fromEntries(
            [
                "kind",
                "id",
                "latitude",
                "longitude",
                "timestamp",
                "report_kind",
                "urgency",
                "affiliation",
                "vehicles",
                "people",
                "place",
                "size",
                "activity",
                "unit",
                "equipment",
            ].map((k) => [k, item[k]])
        );
        record.withdrawn = true;
    } else record = { kind: "alert", id: item.id, active: false, alert_kind: item.alert_kind, note: "" };
    return run((token, owner) => send(record, token, owner));
}
onBeforeUnmount(() => {
    generation++;
});
</script>
