<template>
    <div v-if="snapshot.available" class="space-y-1" aria-label="MeshCore navigation">
        <div v-for="section in sections" :key="section.id">
            <button
                type="button"
                class="flex w-full items-center gap-2 py-2.5 text-sm font-semibold rounded-r-full text-sem-fg hover:bg-sem-surface-muted"
                :class="collapsed ? 'justify-center' : 'pl-2 pr-3'"
                :aria-label="section.label"
                :title="section.label"
                :aria-expanded="!collapsed && expanded[section.id]"
                @click="toggle(section)"
            >
                <span class="relative shrink-0"
                    ><MaterialDesignIcon :icon-name="section.icon" class="size-6" /><span
                        v-if="collapsed && section.unread"
                        class="absolute -top-1 -right-2 text-[10px] rounded-full px-1 bg-sem-danger text-white"
                        >{{ section.unread }}</span
                    ></span
                >
                <template v-if="!collapsed"
                    ><span class="min-w-0 flex-1 text-left truncate">{{ section.label }}</span
                    ><span v-if="section.unread" class="text-xs text-sem-accent">{{ section.unread }}</span
                    ><MaterialDesignIcon
                        :icon-name="expanded[section.id] ? 'chevron-down' : 'chevron-right'"
                        class="size-4"
                /></template>
            </button>
            <div v-if="!collapsed" v-show="expanded[section.id]" class="pl-5 pr-2 space-y-0.5">
                <RouterLink
                    v-for="row in section.rows"
                    :key="row.key"
                    :to="row.to"
                    class="flex items-center gap-2 rounded-lg px-2 py-1.5 text-xs text-sem-fg-muted hover:bg-sem-surface-muted"
                    active-class="bg-sem-surface-muted text-sem-accent"
                >
                    <MaterialDesignIcon :icon-name="row.icon" class="size-4 shrink-0" /><span class="truncate flex-1">{{
                        row.name
                    }}</span
                    ><MaterialDesignIcon
                        v-if="row.muted || row.mentions_only"
                        :icon-name="row.muted ? 'bell-off-outline' : 'at'"
                        class="size-3 shrink-0"
                    /><span v-if="row.unread" class="font-bold text-sem-accent">{{ row.unread }}</span>
                </RouterLink>
                <RouterLink
                    :to="{
                        name: section.route,
                        ...(snapshot.radio_id ? { query: { meshcoreRadio: snapshot.radio_id } } : {}),
                    }"
                    class="block px-2 py-1.5 text-xs text-sem-accent hover:underline"
                    >{{ section.id === "channels" ? "Manage channels" : "View saved nodes" }}</RouterLink
                >
            </div>
        </div>
    </div>
</template>
<script setup>
import { computed, reactive } from "vue";
import MaterialDesignIcon from "../MaterialDesignIcon.vue";
import { useMeshCoreUi, meshcoreChannelRoute, meshcoreNodeRoute } from "../../js/meshcoreUi";
const props = defineProps({ collapsed: Boolean });
const { snapshot } = useMeshCoreUi();
const expanded = reactive({ channels: false, nodes: false });
const sections = computed(() => [
    {
        id: "channels",
        label: "MeshCore Channels",
        icon: "pound",
        route: "meshcore-channels",
        unread: (snapshot.value.channels || []).reduce((n, row) => n + (row.hidden ? 0 : row.unread || 0), 0),
        rows: (snapshot.value.channels || [])
            .filter((row) => !row.hidden)
            .map((row) => ({
                key: row.channel_id + ":" + row.slot,
                to: meshcoreChannelRoute(row.channel_id, snapshot.value.radio_id),
                name: row.name,
                icon: row.kind === "private" ? "lock-outline" : "pound",
                unread: row.unread,
                muted: row.muted,
                mentions_only: row.mentions_only,
            })),
    },
    {
        id: "nodes",
        label: "MeshCore Nodes",
        icon: "radio-tower",
        route: "meshcore-nodes",
        unread: (snapshot.value.nodes || []).reduce((n, row) => n + (row.unread || 0), 0),
        rows: (snapshot.value.nodes || []).map((row) => ({
            key: row.peer,
            unread: row.unread || 0,
            to: meshcoreNodeRoute(row.peer, snapshot.value.radio_id),
            name: row.name || "MeshCore node",
            icon: row.kind === 3 ? "forum-outline" : row.kind === 4 ? "access-point" : "radio-tower",
        })),
    },
]);
import { useRouter } from "vue-router";
const router = useRouter();
function toggle(section) {
    if (props.collapsed)
        router.push({
            name: section.route,
            ...(snapshot.value.radio_id ? { query: { meshcoreRadio: snapshot.value.radio_id } } : {}),
        });
    else expanded[section.id] = !expanded[section.id];
}
</script>
