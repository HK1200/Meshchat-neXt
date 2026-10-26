<template>
    <section
        v-if="snapshot.available && snapshot.channel_banishments?.length"
        class="border-b border-sem-border py-4 space-y-3"
        aria-label="MeshCore channel banishments"
    >
        <h2 class="font-semibold text-sem-fg">MeshCore channel sender names</h2>
        <p class="text-xs text-sem-fg-muted">
            Local filters by displayed name, scoped to each channel. Names are not verified identities.
        </p>
        <p v-if="error" role="alert" class="text-xs text-sem-danger">{{ error }}</p>
        <div
            v-for="row in visible"
            :key="row.channel_id + ':' + row.sender"
            class="flex items-center gap-3 border-b border-sem-border/60 py-2"
        >
            <MaterialDesignIcon icon-name="account-cancel-outline" class="size-6 text-sem-fg-muted" />
            <div class="min-w-0 flex-1">
                <strong class="text-sm text-sem-fg">{{ row.sender }}</strong>
                <p class="text-xs text-sem-fg-muted">
                    MeshCore · {{ row.channel_name || row.channel_id.slice(0, 12) + "…" }} · local name filter
                </p>
            </div>
            <button type="button" class="secondary-chip" :disabled="busy" @click="lift(row)">Lift banishment</button>
        </div>
    </section>
</template>
<script setup>
import { computed, ref, watch } from "vue";
import MaterialDesignIcon from "../MaterialDesignIcon.vue";
import { useMeshCoreUi } from "../../js/meshcoreUi";
const props = defineProps({ search: { type: String, default: "" }, sort: { type: String, default: "newest" } });
const { snapshot, error, action, refresh } = useMeshCoreUi();
defineExpose({ refresh });
const busy = ref(false);
const emit = defineEmits(["count"]);
watch(
    () => snapshot.value.channel_banishments,
    (rows) => emit("count", rows?.length || 0),
    { immediate: true }
);
const visible = computed(() =>
    (snapshot.value.channel_banishments || [])
        .filter((row) => `${row.sender} ${row.channel_name || ""}`.toLowerCase().includes(props.search.toLowerCase()))
        .sort((a, b) =>
            props.sort === "name"
                ? a.sender.localeCompare(b.sender)
                : props.sort === "oldest"
                  ? a.created - b.created
                  : b.created - a.created
        )
);
async function lift(row) {
    busy.value = true;
    try {
        await action("channel-unbanish", { channel: row.channel_id, sender: row.sender });
    } catch {
        error.value = "Could not lift this MeshCore banishment.";
    } finally {
        busy.value = false;
    }
}
</script>
