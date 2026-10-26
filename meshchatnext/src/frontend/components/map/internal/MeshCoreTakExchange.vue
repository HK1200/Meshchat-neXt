<template>
    <details class="rounded-lg border border-sem-border p-2 text-xs" aria-label="TAK file exchange">
        <summary class="cursor-pointer">TAK files · local import / export</summary>
        <div class="space-y-2 mt-2">
            <p>
                Points and drawings. Files contain coordinates and labels, without channel keys. Import previews stay
                here until you explicitly share an item.
            </p>
            <p>
                Lines, boundaries, circles and routes retain their geometry. Original TAK identity/affiliation is not
                inferred. Imported items are unverified; labels and notes are shortened to fit MeshCore.
            </p>
            <label class="flex gap-2"
                ><input v-model="includeMedia" type="checkbox" /> Include already downloaded photos and voice
                attachments</label
            >
            <p>
                Only local cached media is included. Missing media and ambiguous senders are reported; no radio
                downloads start here.
            </p>
            <button type="button" class="secondary-chip" :disabled="busy || !exportable.length" @click="exportPackage">
                Export {{ exportable.length }} map items as TAK package
            </button>
            <label class="block"
                >Preview a CoT file or TAK ZIP package (up to 10 MB)
                <input type="file" accept=".cot,.xml,.zip" :disabled="busy" @change="importFile" />
            </label>
            <p v-if="skipped">{{ skipped }} non-CoT entries omitted.</p>
            <ul class="space-y-2">
                <li v-for="(item, i) in preview" :key="i" class="rounded border border-sem-border p-2">
                    <p class="font-semibold">{{ item.label }}</p>
                    <p>{{ item.latitude.toFixed(5) }}, {{ item.longitude.toFixed(5) }}</p>
                    <p>{{ item.note }}</p>
                    <p v-if="item.stale">Source expiry: {{ item.stale }}</p>
                    <button type="button" class="secondary-chip" @click="$emit('focus', item)">View on map</button>
                    <template v-if="item.kind === 'shape'">
                        <p>{{ shapeNames[item.shape_kind] }} · {{ item.points.length }} vertices</p>
                        <button
                            type="button"
                            class="secondary-chip"
                            :disabled="busy || !canShare"
                            @click="checkSize(item, i)"
                        >
                            Check radio size
                        </button>
                        <p v-if="sizes[i]">{{ sizes[i].bytes }} / {{ sizes[i].limit }} bytes</p>
                    </template>
                    <button
                        type="button"
                        class="secondary-chip"
                        :disabled="busy || !canShare || (item.kind === 'shape' && !sizes[i])"
                        @click="share(item)"
                    >
                        {{ item.kind === "shape" ? "Share as MeshCore drawing" : "Share as MeshCore pin" }}
                    </button>
                </li>
            </ul>
            <ul class="space-y-2" aria-label="Package attachments">
                <li
                    v-for="(file, index) in files"
                    :key="file.path || index"
                    class="rounded border border-sem-border p-2"
                >
                    <p class="break-all">{{ file.name }} · {{ Math.ceil(file.bytes.length / 1024) }} KB</p>
                    <button type="button" class="secondary-chip" @click="openFile(file)">Preview attachment</button>
                    <button type="button" class="secondary-chip" @click="saveFile(file)">Save attachment</button>
                </li>
            </ul>
            <img
                v-if="localPreview?.type.startsWith('image/')"
                :src="localPreview.url"
                class="max-w-full max-h-64 object-contain"
                alt="Imported TAK attachment"
            />
            <audio v-if="localPreview?.type.startsWith('audio/')" :src="localPreview.url" controls preload="none" />
            <button
                v-if="preview.length || files.length"
                type="button"
                class="secondary-chip"
                :disabled="busy"
                @click="saveReviewed"
            >
                Save reviewed TAK package
            </button>
            <button v-if="preview.length || files.length" type="button" class="secondary-chip" @click="clear">
                Clear preview
            </button>
            <p v-if="notice" role="status">{{ notice }}</p>
            <p v-if="problem" role="alert" class="text-sem-danger">{{ problem }}</p>
        </div>
    </details>
</template>
<script setup>
/* eslint-disable security/detect-possible-timing-attacks -- Public lifetime counters, not secret comparisons. */
import { computed, ref, watch, onBeforeUnmount } from "vue";
import { readCot, readTakPackage, writeTakPackage } from "../../../js/meshcoreCot";
import { meshcoreCotRecord } from "../../../js/meshcoreCotGeometry";
import { attachmentContacts } from "../../../js/meshcoreAttachments";
import { photoDimensions } from "../../../js/meshcorePhotos";
import { apiPath } from "../../../js/constants";
const props = defineProps({
    owner: { type: String, default: null },
    team: { type: Object, default: null },
    scope: { type: String, default: null },
    connected: Boolean,
    supported: Boolean,
    incomingPackage: { type: Object, default: null },
    contacts: { type: Array, default: () => [] },
});
const emit = defineEmits(["focus", "refresh"]);
const preview = ref([]),
    skipped = ref(0),
    busy = ref(false),
    problem = ref(""),
    notice = ref("");
const sizes = ref({});
const files = ref([]),
    includeMedia = ref(false),
    localPreview = ref(null);
const shapeNames = ["Line", "Freehand", "Polygon", "Rectangle", "Circle", "Route"];
let generation = 0;
const canShare = computed(
    () => props.connected && props.supported && props.team?.enabled && props.owner && props.team?.channel_id
);
const exportable = computed(() =>
    (props.team?.records || [])
        .filter(
            (r) =>
                !r.deleted &&
                !r.withdrawn &&
                (r.kind !== "alert" || r.active) &&
                (r.kind === "shape" || (Number.isFinite(r.latitude) && Number.isFinite(r.longitude)))
        )
        .slice(0, 100)
);
function clear() {
    generation++;
    preview.value = [];
    sizes.value = {};
    files.value = [];
    if (localPreview.value) URL.revokeObjectURL(localPreview.value.url);
    localPreview.value = null;
    skipped.value = 0;
    busy.value = false;
    notice.value = "";
    problem.value = "";
}
watch([() => props.owner, () => props.team?.channel_id, () => props.scope, () => props.team?.enabled], clear);
watch(
    () => props.incomingPackage,
    async (value) => {
        if (!value || value.owner !== props.owner) return;
        clear();
        const token = generation;
        busy.value = true;
        try {
            const result = await readTakPackage(value.bytes);
            if (token !== generation) return;
            preview.value = result.items;
            files.value = result.files || [];
            skipped.value = result.skipped;
            notice.value = "Server package preview loaded. Nothing sent to the radio.";
        } catch (error) {
            if (token === generation)
                problem.value =
                    error.message ||
                    "Could not preview this package. You can save the original from the server controls.";
        } finally {
            if (token === generation) busy.value = false;
        }
    }
);
async function importFile(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    clear();
    if (!file) return;
    const token = generation;
    busy.value = true;
    try {
        if (file.size > 10 * 1024 * 1024) throw new Error("Choose a file smaller than 10 MB.");
        const result = file.name.toLowerCase().endsWith(".zip")
            ? await readTakPackage(await file.arrayBuffer())
            : { items: readCot(await file.text()), skipped: 0 };
        if (token !== generation) return;
        preview.value = result.items;
        skipped.value = result.skipped;
        files.value = result.files || [];
        notice.value = "Preview loaded. Nothing sent to the radio.";
    } catch (error) {
        if (token === generation) problem.value = error.message || "Could not read this file.";
    } finally {
        if (token === generation) busy.value = false;
    }
}
async function exportPackage() {
    const token = generation;
    busy.value = true;
    problem.value = "";
    try {
        const items = exportable.value.map((item, index) => ({ ...item, sourceUid: `local-${index}` }));
        const attachments = [];
        let missing = 0,
            totalMedia = 0,
            overflow = false;
        if (includeMedia.value)
            for (const item of items) {
                if (!item.attachment) continue;
                const own = item.alias === props.owner?.slice(0, 8);
                const matches = attachmentContacts(props.contacts, item.alias);
                const peer = own ? props.owner : matches.length === 1 ? matches[0].peer : null;
                if (!peer) {
                    missing++;
                    continue;
                }
                try {
                    const { data } = await window.api.post(apiPath("/meshcore/voice-play"), {
                        peer,
                        sid: item.attachment.sid,
                        direction: own ? "out" : "in",
                        expected_owner: props.owner,
                    });
                    if (token !== generation) return;
                    const result = data.result,
                        raw = result.png_base64 || result.wav_base64;
                    if (!raw) {
                        missing++;
                        continue;
                    }
                    const bytes = Uint8Array.from(atob(raw), (c) => c.charCodeAt(0));
                    if (totalMedia + bytes.length > 9 * 1024 * 1024) {
                        overflow = true;
                        break;
                    }
                    totalMedia += bytes.length;
                    attachments.push({
                        uid: item.sourceUid,
                        name: `attachment-${item.attachment.sid}.${result.png_base64 ? "png" : "wav"}`,
                        bytes,
                    });
                } catch {
                    missing++;
                }
            }
        if (overflow)
            throw new Error(
                "Cached attachments exceed the package size limit. Export fewer items or turn off media export."
            );
        const bytes = await writeTakPackage(items, { files: attachments });
        if (token !== generation) return;
        const url = URL.createObjectURL(new Blob([bytes], { type: "application/zip" }));
        const a = document.createElement("a");
        a.href = url;
        a.download = "meshcore-points.zip";
        a.rel = "noopener";
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
        notice.value = `Local package prepared. No radio traffic sent.${missing ? ` ${missing} unavailable attachments omitted.` : ""}`;
    } catch (error) {
        if (token === generation) problem.value = error.message || "Could not export points.";
    } finally {
        if (token === generation) busy.value = false;
    }
}
function download(bytes, name, type = "application/octet-stream") {
    const url = URL.createObjectURL(new Blob([bytes], { type }));
    const anchor = document.createElement("a");
    anchor.href = url;
    // eslint-disable-next-line no-control-regex -- Remove control characters from untrusted filenames.
    anchor.download = name.replace(/[\x00-\x1f\\/:*?"<>|]/g, "_");
    anchor.rel = "noopener";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function saveFile(file) {
    download(file.bytes, file.name);
}
function openFile(file) {
    const bytes = file.bytes;
    let type = "";
    if (bytes[0] === 137 && bytes[1] === 80) type = "image/png";
    else if (bytes[0] === 255 && bytes[1] === 216) type = "image/jpeg";
    else if (String.fromCharCode(...bytes.slice(8, 12)) === "WEBP") type = "image/webp";
    else if (
        String.fromCharCode(...bytes.slice(0, 4)) === "RIFF" &&
        String.fromCharCode(...bytes.slice(8, 12)) === "WAVE"
    )
        type = "audio/wav";
    else if (String.fromCharCode(...bytes.slice(0, 4)) === "OggS") type = "audio/ogg";
    if (!type) {
        problem.value = "Preview unavailable for this file type. You can save it locally.";
        return;
    }
    try {
        if (type.startsWith("image/")) {
            const size = photoDimensions(bytes.slice(0, 1048576), type);
            if (size.width * size.height > 4000000) throw new Error("Save this large image to view it in another app.");
        }
        if (localPreview.value) URL.revokeObjectURL(localPreview.value.url);
        localPreview.value = { type, url: URL.createObjectURL(new Blob([bytes], { type })) };
    } catch (error) {
        problem.value = error.message || "Preview unavailable.";
    }
}
async function saveReviewed() {
    const token = generation;
    busy.value = true;
    problem.value = "";
    try {
        const bytes = await writeTakPackage(preview.value, { files: files.value });
        if (token === generation) download(bytes, "meshcore-reviewed-package.zip", "application/zip");
    } catch (error) {
        if (token === generation) problem.value = error.message || "Could not save package.";
    } finally {
        if (token === generation) busy.value = false;
    }
}
async function checkSize(item, index) {
    const token = generation;
    busy.value = true;
    problem.value = "";
    try {
        const { data } = await window.api.post(apiPath("/meshcore/team-shape-preview"), {
            record: meshcoreCotRecord(item),
            expected_owner: props.owner,
        });
        if (token === generation) sizes.value[index] = data.result;
    } catch {
        if (token === generation)
            problem.value =
                "This drawing does not fit a MeshCore packet. Simplify or split it explicitly before sharing.";
    } finally {
        if (token === generation) busy.value = false;
    }
}
async function share(item) {
    if (!canShare.value || busy.value) return;
    const token = generation;
    busy.value = true;
    problem.value = "";
    notice.value = "";
    const record = meshcoreCotRecord(item);
    try {
        const { data } = await window.api.post(apiPath("/meshcore/team-send"), {
            record,
            request_id: crypto.randomUUID(),
            expected_owner: props.owner,
            expected_channel_id: props.team.channel_id,
            expected_scope: props.scope,
        });
        if (token !== generation) return;
        notice.value =
            data.result?.state === "submitted"
                ? `${item.kind === "shape" ? "Drawing" : "Pin"} submitted to MeshCore. Channel delivery is not acknowledged.`
                : "Transmission was not confirmed. No automatic retry.";
        emit("refresh");
    } catch {
        if (token === generation) problem.value = "Could not share this point. Check the connection before retrying.";
    } finally {
        if (token === generation) busy.value = false;
    }
}
onBeforeUnmount(clear);
</script>
