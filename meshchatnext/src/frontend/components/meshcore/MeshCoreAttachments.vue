<template>
    <div class="shrink-0 border-t border-sem-border px-3 py-2" aria-label="MeshCore attachments">
        <div class="flex items-center gap-2 text-xs">
            <span class="text-sem-fg-muted mr-auto">Attachments · Radio2</span>
            <button type="button" class="secondary-chip" :aria-expanded="active === 'photo'" @click="toggle('photo')">
                Photo
            </button>
            <button type="button" class="secondary-chip" :aria-expanded="active === 'voice'" @click="toggle('voice')">
                Voice clip
            </button>
            <button v-if="active" type="button" class="p-2" aria-label="Close attachments" @click="active = ''">
                ×
            </button>
        </div>
        <AppModal
            :model-value="Boolean(active)"
            title="Attachments · MeshCore Radio2"
            :max-width="720"
            :show-close="true"
            body-class="min-h-0 flex-1 overflow-y-auto overscroll-contain p-4"
            @update:model-value="onVisibleUpdate"
            @close="active = ''"
        >
            <div class="flex gap-2 mb-3">
                <button
                    type="button"
                    class="secondary-chip"
                    :aria-pressed="active === 'photo'"
                    @click="toggle('photo')"
                >
                    Photo
                </button>
                <button
                    type="button"
                    class="secondary-chip"
                    :aria-pressed="active === 'voice'"
                    @click="toggle('voice')"
                >
                    Voice clip
                </button>
            </div>
            <p class="text-xs text-sem-fg-muted mb-2">Closing or switching attachment type discards this draft.</p>
            <MeshCoreImageComposer v-if="active === 'photo'" embedded v-bind="$props" @sent="$emit('sent')" />
            <MeshCoreVoiceComposer
                v-else-if="active === 'voice'"
                embedded
                v-bind="$props"
                :channel="Boolean(channelId)"
                @sent="$emit('sent')"
            />
        </AppModal>
    </div>
</template>
<script setup>
import { ref, watch } from "vue";
import AppModal from "../AppModal.vue";
import MeshCoreImageComposer from "./MeshCoreImageComposer.vue";
import MeshCoreVoiceComposer from "./MeshCoreVoiceComposer.vue";
const props = defineProps({
    peer: { type: String, required: true },
    owner: { type: String, default: "" },
    connected: Boolean,
    channelId: { type: String, default: "" },
    scope: { type: String, default: null },
});
defineEmits(["sent"]);
const active = ref("");
function onVisibleUpdate(value) {
    if (!value) active.value = "";
}
function toggle(type) {
    active.value = active.value === type ? "" : type;
}
watch(
    () => [props.owner, props.peer, props.channelId, props.scope],
    () => {
        active.value = "";
    }
);
</script>
