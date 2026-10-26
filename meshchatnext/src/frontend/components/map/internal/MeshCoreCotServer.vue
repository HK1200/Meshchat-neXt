<template>
    <details
        class="rounded-lg border border-sem-border p-2 text-xs"
        aria-label="Optional TAK server"
        @toggle="opened = $event.target.open"
    >
        <summary class="cursor-pointer">TAK server · optional</summary>
        <div class="space-y-2 mt-2">
            <p>
                Connect only when you choose. Supports TLS-encrypted map items with XML or negotiated TAK v1. No
                automatic location sharing, MeshCore forwarding, Reticulum bridge or reconnection.
            </p>
            <p>
                Server address and certificates are used for this session only. Disconnecting clears received previews.
                Certificate enrollment and package transfer use the same verified server. Nothing is forwarded
                automatically.
            </p>
            <template v-if="!server.connected">
                <label class="block"
                    >Server address<input
                        v-model.trim="host"
                        class="input-field w-full"
                        autocomplete="off"
                        :disabled="busy"
                /></label>
                <label class="block"
                    >Port<input
                        v-model.number="port"
                        type="number"
                        min="1"
                        max="65535"
                        class="input-field w-full"
                        :disabled="busy"
                /></label>
                <label class="block"
                    >HTTPS package port<input
                        v-model.number="httpsPort"
                        type="number"
                        min="1"
                        max="65535"
                        class="input-field w-full"
                        :disabled="busy"
                /></label>
                <label class="flex gap-2"
                    ><input v-model="autoProtocol" type="checkbox" :disabled="busy" /> Negotiate TAK v1 when
                    supported</label
                >
                <label class="block"
                    >Username (if required)<input
                        v-model="username"
                        class="input-field w-full"
                        autocomplete="off"
                        :disabled="busy"
                /></label>
                <label class="block"
                    >Password<input
                        v-model="password"
                        :type="showPassword ? 'text' : 'password'"
                        class="input-field w-full"
                        autocomplete="off"
                        :disabled="busy"
                /></label>
                <label class="flex gap-2"><input v-model="showPassword" type="checkbox" /> Show password</label>
                <details class="rounded border border-sem-border p-2">
                    <summary>Enroll a client certificate</summary>
                    <p>
                        Creates a private key locally and requests a certificate for this account. The key stays in the
                        local backend. Enrollment is kept for this session only.
                    </p>
                    <label class="block"
                        >Enrollment HTTPS port<input
                            v-model.number="enrollPort"
                            type="number"
                            min="1"
                            max="65535"
                            class="input-field"
                            :disabled="busy"
                    /></label>
                    <button
                        type="button"
                        class="secondary-chip"
                        :disabled="busy || !host || !username || !password"
                        @click="enrollCertificate"
                    >
                        Enroll certificate
                    </button>
                </details>
                <label class="block"
                    >Server CA certificate · PEM (optional)<input
                        type="file"
                        accept=".pem,.crt"
                        :disabled="busy"
                        @change="certificateFile($event, 'ca')"
                /></label>
                <label class="block"
                    >Client certificate · PEM (if required)<input
                        type="file"
                        accept=".pem,.crt"
                        :disabled="busy"
                        @change="certificateFile($event, 'certificate')"
                /></label>
                <label class="block"
                    >Client private key · unencrypted PEM (if required)<input
                        type="file"
                        accept=".pem,.key"
                        :disabled="busy"
                        @change="certificateFile($event, 'private_key')"
                /></label>
                <p>
                    Certificates are checked, including the server name. Ask your server administrator for compatible
                    files. Client-key files are loaded locally and removed from temporary storage after loading.
                </p>
                <button
                    type="button"
                    class="secondary-chip"
                    :disabled="busy || !owner || !connected || !host"
                    @click="connect"
                >
                    Connect TAK server
                </button>
            </template>
            <button v-else type="button" class="secondary-chip" :disabled="busy" @click="disconnect">
                Disconnect TAK server
            </button>
            <p role="status">{{ server.state || "Disconnected" }}</p>
            <p v-if="server.dropped">{{ server.dropped }} unsupported events omitted.</p>
            <template v-if="server.connected">
                <label class="block"
                    >Send one team map item to this server<select v-model.number="selected" class="input-field w-full">
                        <option :value="-1">Choose a point</option>
                        <option v-for="(item, i) in points" :key="i" :value="i">
                            {{ item.label || item.callsign || item.kind }}
                        </option>
                    </select></label
                >
                <button type="button" class="secondary-chip" :disabled="busy || !points[selected]" @click="sendPoint">
                    Send selected item to TAK server
                </button>
            </template>
            <ul class="space-y-2">
                <li v-for="(item, i) in server.items || []" :key="i" class="rounded border border-sem-border p-2">
                    <p class="font-semibold">{{ item.label }} · TAK / unverified</p>
                    <p>{{ item.latitude.toFixed(5) }}, {{ item.longitude.toFixed(5) }}</p>
                    <p>{{ item.note }}</p>
                    <p v-if="item.stale">Source expiry: {{ item.stale }}</p>
                    <button type="button" class="secondary-chip" @click="$emit('focus', item)">View on map</button>
                    <template v-if="item.kind === 'shape'"
                        ><p>Drawing · {{ item.points.length }} vertices</p>
                        <button
                            type="button"
                            class="secondary-chip"
                            :disabled="busy || !team?.enabled || !connected"
                            @click="checkShape(item)"
                        >
                            Check radio size
                        </button>
                        <p v-if="sizes[shapeKey(item)]">
                            {{ sizes[shapeKey(item)].bytes }} / {{ sizes[shapeKey(item)].limit }} bytes
                        </p></template
                    >
                    <button
                        type="button"
                        class="secondary-chip"
                        :disabled="
                            busy || !team?.enabled || !connected || (item.kind === 'shape' && !sizes[shapeKey(item)])
                        "
                        @click="share(item)"
                    >
                        {{ item.kind === "shape" ? "Share as MeshCore drawing" : "Share as MeshCore pin" }}
                    </button>
                </li>
            </ul>
            <details v-if="server.connected" class="rounded border border-sem-border p-2">
                <summary>TAK server packages</summary>
                <p>
                    Transfers use HTTPS, not LoRa. Downloads are checked against their SHA-256 hash and are never sent
                    to a radio automatically.
                </p>
                <label class="block"
                    >Search<input v-model="keywords" class="input-field w-full" maxlength="128"
                /></label>
                <button type="button" class="secondary-chip" :disabled="busy" @click="searchPackages">
                    Search server packages
                </button>
                <ul>
                    <li v-for="row in packages" :key="row.hash">
                        <p>{{ row.name }}</p>
                        <button
                            type="button"
                            class="secondary-chip"
                            :disabled="busy"
                            @click="downloadPackage(row.hash)"
                        >
                            Download for review
                        </button>
                    </li>
                </ul>
                <label class="block"
                    >Or enter package SHA-256<input
                        v-model.trim="packageHash"
                        class="input-field w-full font-mono"
                        maxlength="64"
                /></label>
                <button
                    type="button"
                    class="secondary-chip"
                    :disabled="busy || !/^[0-9a-f]{64}$/.test(packageHash)"
                    @click="downloadPackage(packageHash)"
                >
                    Download package for review
                </button>
                <button v-if="downloaded" type="button" class="secondary-chip" @click="saveOriginal">
                    Save original package
                </button>
                <label class="flex gap-2"
                    ><input v-model="privateUpload" type="checkbox" /> Keep uploaded packages private on the
                    server</label
                >
                <label class="block"
                    >Upload a TAK package (up to 10 MB)<input
                        type="file"
                        accept=".zip"
                        :disabled="busy"
                        @change="uploadPackage"
                /></label>
            </details>
            <p v-if="notice" role="status">{{ notice }}</p>
            <p v-if="problem" role="alert" class="text-sem-danger">{{ problem }}</p>
        </div>
    </details>
</template>
<script setup>
/* eslint-disable security/detect-possible-timing-attacks -- Public lifetime counters are not secrets. */
import { ref, computed, watch, onBeforeUnmount } from "vue";
import { apiPath } from "../../../js/constants";
import { meshcoreCotRecord } from "../../../js/meshcoreCotGeometry";
import { cotPoint, readCot } from "../../../js/meshcoreCot";
import DialogUtils from "../../../js/DialogUtils";
const props = defineProps({
    owner: { type: String, default: null },
    team: { type: Object, default: null },
    scope: { type: String, default: null },
    connected: Boolean,
});
const emit = defineEmits(["focus", "refresh", "package"]);
const opened = ref(false),
    host = ref(""),
    port = ref(8089),
    server = ref({}),
    busy = ref(false),
    problem = ref(""),
    notice = ref(""),
    selected = ref(-1);
let generation = 0;
let certificates = {};
const httpsPort = ref(8443),
    enrollPort = ref(8446),
    autoProtocol = ref(true),
    username = ref(""),
    password = ref(""),
    showPassword = ref(false);
const keywords = ref(""),
    packages = ref([]),
    packageHash = ref(""),
    privateUpload = ref(true),
    downloaded = ref(null),
    sizes = ref({});
const points = computed(() =>
    (props.team?.records || []).filter(
        (r) =>
            !r.deleted &&
            !r.withdrawn &&
            (r.kind !== "alert" || r.active) &&
            (r.kind === "shape" || (Number.isFinite(r.latitude) && Number.isFinite(r.longitude)))
    )
);
async function certificateFile(event, name) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    const token = generation;
    try {
        if (file.size > 32768) throw new Error("Certificate files must be smaller than 32 KB.");
        const text = await file.text();
        if (token === generation) {
            certificates[name] = text;
            notice.value = "Certificate loaded for this session.";
        }
    } catch (error) {
        problem.value = error.message;
    }
}
async function refresh() {
    if (!opened.value || !props.owner || !props.connected) return;
    const token = generation;
    try {
        const { data } = await window.api.get(apiPath("/meshcore/tak-status"), { params: { owner: props.owner } });
        if (token === generation) server.value = data.result || {};
    } catch {
        /* Connection status remains visible until next explicit action. */
    }
}
async function action(endpoint, body, message) {
    const token = generation;
    busy.value = true;
    problem.value = "";
    notice.value = "";
    try {
        const { data } = await window.api.post(apiPath(`/meshcore/${endpoint}`), {
            ...body,
            expected_owner: props.owner,
        });
        if (token !== generation) return;
        notice.value =
            endpoint === "team-send" && data.result?.state !== "submitted"
                ? "MeshCore transmission was not confirmed. No automatic retry."
                : message;
        await refresh();
        return data.result;
    } catch {
        if (token === generation)
            problem.value =
                "Request failed. Check the connection, server address and certificates. No automatic retry.";
    } finally {
        if (token === generation) busy.value = false;
    }
}
async function connect() {
    await action(
        "tak-connect",
        {
            host: host.value,
            port: port.value,
            https_port: httpsPort.value,
            auto_protocol: autoProtocol.value,
            username: username.value,
            password: password.value,
            ...certificates,
        },
        "TAK TLS session opened. Nothing forwarded to MeshCore."
    );
    certificates = {};
    password.value = "";
}
async function disconnect() {
    await action("tak-disconnect", {}, "Disconnected. Received previews cleared.");
    server.value = {};
}
async function sendPoint() {
    if (!props.connected || busy.value) return;
    const point = points.value[selected.value];
    if (!point) return;
    const record =
        point.kind === "shape"
            ? meshcoreCotRecord(point)
            : {
                  latitude: point.latitude,
                  longitude: point.longitude,
                  label: (point.label || point.callsign || "MeshCore point").slice(0, 128),
                  note: (point.note || point.place || "").slice(0, 256),
              };
    const token = generation;
    if (!(await DialogUtils.confirm("Send this map item’s coordinates and label to the connected TAK server?"))) return;
    if (token !== generation) return;
    await action("tak-send", { record }, "Map item submitted to TAK server; delivery is not acknowledged.");
}
async function share(item) {
    if (!props.connected || !props.team?.enabled || busy.value) return;
    const point = readCot(cotPoint(item))[0];
    const record = meshcoreCotRecord(point);
    await action(
        "team-send",
        {
            record,
            request_id: crypto.randomUUID(),
            expected_channel_id: props.team?.channel_id,
            expected_scope: props.scope,
        },
        "Pin submitted to MeshCore; channel delivery is not acknowledged."
    );
    emit("refresh");
}
function preparedItem(item) {
    return meshcoreCotRecord(readCot(cotPoint(item))[0]);
}
function shapeKey(item) {
    return JSON.stringify(preparedItem(item));
}
async function checkShape(item) {
    const result = await action("team-shape-preview", { record: preparedItem(item) }, "Radio size checked.");
    if (result) sizes.value[shapeKey(item)] = result;
}
async function enrollCertificate() {
    const token = generation;
    if (
        !(await DialogUtils.confirm(
            "Request a client certificate from this TAK server for the entered account? The private key is generated and kept locally for this session."
        ))
    )
        return;
    if (token !== generation) return;
    await action(
        "tak-enroll",
        {
            host: host.value,
            port: enrollPort.value,
            username: username.value,
            password: password.value,
            ca: certificates.ca || "",
        },
        "Certificate enrolled for this session. Connect to use it."
    );
}
async function searchPackages() {
    const result = await action("tak-package-search", { keywords: keywords.value }, "Package search complete.");
    if (result) packages.value = result;
}
async function downloadPackage(digest) {
    const result = await action(
        "tak-package-download",
        { digest },
        "Package downloaded and hash verified. Review it in TAK files before sharing."
    );
    if (!result) return;
    const bytes = Uint8Array.from(atob(result.zip_base64), (c) => c.charCodeAt(0));
    downloaded.value = { bytes, digest };
    emit("package", { bytes, owner: props.owner });
}
function saveOriginal() {
    if (!downloaded.value) return;
    const url = URL.createObjectURL(new Blob([downloaded.value.bytes], { type: "application/zip" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `tak-${downloaded.value.digest.slice(0, 12)}.zip`;
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
}
async function uploadPackage(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || busy.value) return;
    const token = generation;
    if (file.size > 10 * 1024 * 1024) {
        problem.value = "Choose a package smaller than 10 MB.";
        return;
    }
    if (
        !(await DialogUtils.confirm(
            `Upload this package to the connected TAK server with ${privateUpload.value ? "private" : "public"} visibility? No transfer announcement is sent.`
        ))
    )
        return;
    if (token !== generation) return;
    const bytes = new Uint8Array(await file.arrayBuffer());
    if (token !== generation) return;
    let binary = "";
    for (let i = 0; i < bytes.length; i += 8192) binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
    const result = await action(
        "tak-package-upload",
        { zip_base64: btoa(binary), name: file.name, private: privateUpload.value },
        "Package uploaded. No radio traffic or transfer announcement sent."
    );
    if (result) packageHash.value = result.hash;
}
watch(opened, refresh);
watch([() => props.owner, () => props.team?.channel_id, () => props.scope, () => props.connected], () => {
    generation++;
    server.value = {};
    packages.value = [];
    downloaded.value = null;
    sizes.value = {};
    password.value = "";
    selected.value = -1;
    certificates = {};
    notice.value = "";
    problem.value = "";
    busy.value = false;
});
const timer = setInterval(refresh, 5000);
onBeforeUnmount(() => {
    generation++;
    certificates = {};
    clearInterval(timer);
});
</script>
