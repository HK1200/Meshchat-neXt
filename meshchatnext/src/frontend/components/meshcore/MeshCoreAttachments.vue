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
        <div v-if="active" class="pt-3 max-h-[45dvh] overflow-y-auto">
            <p class="text-xs text-sem-fg-muted mb-2">Closing or switching attachment type discards this draft.</p>
            <MeshCoreImageComposer v-if="active === 'photo'" embedded v-bind="$props" @sent="$emit('sent')" />
            <MeshCoreVoiceComposer
                v-else
                embedded
                v-bind="$props"
                :channel="Boolean(channelId)"
                @sent="$emit('sent')"
            />
        </div>
    </div>
</template>
<script setup>
import { ref, watch } from "vue";
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
