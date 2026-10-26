<!-- SPDX-License-Identifier: 0BSD -->

<template>
    <div class="space-y-3">
        <div class="flex items-center bg-sem-surface-muted rounded-lg p-0.5">
            <button
                type="button"
                class="flex-1 px-2 py-1.5 text-[11px] font-medium rounded-md"
                :class="
                    !offlineEnabled ? 'bg-sem-surface dark:bg-sem-surface-muted text-sem-info' : 'text-sem-fg-muted'
                "
                @click="$emit('toggle-offline', false)"
            >
                {{ $t("map.online_mode") }}
            </button>
            <button
                type="button"
                class="flex-1 px-2 py-1.5 text-[11px] font-medium rounded-md"
                :class="offlineEnabled ? 'bg-sem-surface dark:bg-sem-surface-muted text-sem-info' : 'text-sem-fg-muted'"
                @click="$emit('toggle-offline', true)"
            >
                {{ $t("map.offline_mode") }}
            </button>
        </div>
        <label class="flex items-center justify-between text-[11px] text-sem-fg-muted">
            <span>{{ $t("map.caching_enabled") }}</span>
            <input :checked="cachingEnabled" type="checkbox" @change="$emit('toggle-caching', $event.target.checked)" />
        </label>
        <button
            type="button"
            class="w-full py-2 text-[10px] font-semibold uppercase rounded-lg bg-sem-action-primary text-sem-action-primary-text"
            @click="$emit('upload')"
        >
            Import map file (.mbtiles)
        </button>
        <div class="rounded-lg border border-amber-500/40 bg-sem-warning/15 p-2 space-y-2">
            <div class="text-[11px] text-sem-fg leading-snug">{{ $t("map.offline_empty_hint") }}</div>
            <button
                type="button"
                class="w-full py-1.5 text-[10px] font-semibold uppercase rounded-lg border border-sem-border"
                @click="$emit('restore-starter')"
            >
                {{ $t("map.restore_starter_tiles") }}
            </button>
        </div>
        <p v-if="offlineEnabled && hasOfflineMap" class="text-[10px] text-sem-fg-muted leading-snug">
            {{ offlineDescription || $t("map.starter_attribution") }}
            <span v-if="offlineAttribution" class="block mt-1">{{ offlineAttribution }}</span>
        </p>
        <div class="rounded-lg border border-sem-border p-2 space-y-2 text-[11px]">
            <p class="font-semibold">PNW &amp; southern BC offline maps</p>
            <p class="text-sem-fg-muted">
                A compact regional overview is included, with towns, main roads and coastlines (zoom 9). World context
                remains available outside the region.
            </p>
            <p class="text-sem-fg-muted">
                Uses an internet connection and about 104 MB of storage. Once installed, no internet is needed for this
                map.
            </p>
            <button
                v-if="download.status !== 'downloading'"
                type="button"
                class="w-full rounded-lg bg-sem-action-primary text-sem-action-primary-text p-3 font-semibold"
                @click="startDownload"
            >
                Download and use regional detail · 104 MB
            </button>
            <div v-else role="status" class="space-y-2">
                <p>
                    Downloading regional detail · {{ Math.round((100 * download.received) / (download.total || 1)) }}%
                </p>
                <progress class="w-full" :value="download.received" :max="download.total || 1" />
                <button type="button" class="rounded-lg border border-sem-border p-2" @click="cancelDownload">
                    Cancel download
                </button>
            </div>
            <p v-if="download.error" role="alert" class="text-sem-danger">{{ download.error }}</p>
            <p v-if="download.status === 'completed'" role="status">
                Regional detail is ready and selected for offline use.
            </p>
            <a
                href="https://github.com/hk1200/Meshchat-neXt/releases/download/v0.1.0/MeshchatNext-PNW-SouthernBC-detail.mbtiles"
                target="_blank"
                rel="noopener noreferrer"
                class="block text-sem-accent underline"
                >Download file manually instead</a
            >
            <p class="text-sem-fg-muted">
                Optional zoom-12 road and town detail for Washington, Oregon, Idaho and southern BC. The download button
                installs and selects the map automatically. For a file downloaded elsewhere, use Import map file above.
                Data: 25 October 2026; not turn-by-turn navigation.
            </p>
        </div>
        <button
            type="button"
            class="w-full py-2 text-[10px] font-semibold uppercase rounded-lg border border-sem-border"
            @click="$emit('export-region')"
        >
            {{ $t("map.data_export_region") }}
        </button>
        <button
            type="button"
            class="w-full py-2 text-[10px] font-semibold uppercase rounded-lg border border-sem-border"
            @click="$emit('clear-cache')"
        >
            {{ $t("map.clear_cache") }}
        </button>
        <label class="block text-[11px] text-sem-fg-muted space-y-1">
            <span>{{ $t("map.storage_path") }}</span>
            <input
                :value="mbtilesDir"
                type="text"
                class="w-full rounded-lg border border-sem-border bg-sem-surface px-2 py-1.5 text-[11px] font-mono"
                @blur="$emit('save-dir', $event.target.value)"
            />
        </label>
        <div
            v-for="file in mbtilesList"
            :key="file.name"
            class="flex items-center justify-between rounded-lg border border-sem-border p-2"
        >
            <div class="min-w-0">
                <div class="text-[11px] font-semibold truncate">{{ file.name }}</div>
                <div class="text-[9px] text-sem-fg-muted">{{ ((file.size || 0) / 1024 / 1024).toFixed(1) }} MB</div>
            </div>
            <div class="flex items-center gap-1">
                <button
                    v-if="!file.is_active"
                    type="button"
                    class="p-1 text-sem-info"
                    @click="$emit('set-active', file.name)"
                >
                    {{ $t("map.set_active") }}
                </button>
                <button type="button" class="p-1 text-sem-danger" @click="$emit('delete-file', file.name)">
                    {{ $t("map.delete") }}
                </button>
            </div>
        </div>
    </div>
</template>

<script>
import { apiPath } from "../../../js/constants";
export default {
    name: "MapOfflinePanel",
    props: {
        offlineEnabled: { type: Boolean, default: false },
        cachingEnabled: { type: Boolean, default: true },
        mbtilesList: { type: Array, default: () => [] },
        mbtilesDir: { type: String, default: "" },
        hasOfflineMap: { type: Boolean, default: false },
        offlineDescription: { type: String, default: "" },
        offlineAttribution: { type: String, default: "" },
    },
    emits: [
        "regional-ready",
        "toggle-offline",
        "toggle-caching",
        "upload",
        "set-active",
        "delete-file",
        "save-dir",
        "clear-cache",
        "export-region",
        "restore-starter",
    ],
    data() {
        return { download: { status: "idle", received: 0, total: 0 }, pollTimer: null, stopped: false };
    },
    mounted() {
        this.refreshDownload();
    },
    beforeUnmount() {
        this.stopped = true;
        clearTimeout(this.pollTimer);
    },
    methods: {
        async refreshDownload() {
            clearTimeout(this.pollTimer);
            if (!window.api?.get) return;
            try {
                const previous = this.download.status;
                this.download = (await window.api.get(apiPath("/map/mbtiles/regional-download"))).data;
                if (this.download.status === "completed" && previous !== "completed") this.$emit("regional-ready");
            } catch {
                /* Keep map imports usable if status is temporarily unavailable. */
            }
            if (!this.stopped && this.download.status === "downloading")
                this.pollTimer = setTimeout(() => this.refreshDownload(), 1000);
        },
        async startDownload() {
            try {
                this.download = (await window.api.post(apiPath("/map/mbtiles/regional-download"), {})).data;
                await this.refreshDownload();
            } catch (error) {
                this.download = {
                    status: "failed",
                    error:
                        error.response?.data?.message ||
                        "Could not start the map download. Check connectivity and Privacy mode, then retry.",
                };
            }
        },
        async cancelDownload() {
            try {
                await window.api.delete(apiPath("/map/mbtiles/regional-download"));
                await this.refreshDownload();
            } catch {
                this.download.error = "Could not cancel the download; please retry.";
            }
        },
    },
};
</script>
