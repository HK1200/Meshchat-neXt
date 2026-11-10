<template>
    <button
        v-if="supported"
        type="button"
        class="px-3 py-2 rounded-full"
        :class="
            speakerOn
                ? 'bg-sem-action-primary text-sem-action-primary-text'
                : 'bg-sem-surface-muted text-sem-fg-secondary'
        "
        :aria-pressed="speakerOn"
        @click="toggle"
    >
        {{ $t("call.speaker") }}
    </button>
</template>

<script>
import ToastUtils from "../../js/ToastUtils";

export default {
    name: "CallSpeakerRoute",
    data() {
        return {
            supported: typeof window.MeshchatNextAndroid?.setTelephoneSpeaker === "function",
            speakerOn: false,
        };
    },
    mounted() {
        this.refresh();
        window.addEventListener("meshchatnext-call-route", this.refresh);
    },
    beforeUnmount() {
        window.removeEventListener("meshchatnext-call-route", this.refresh);
    },
    methods: {
        refresh() {
            this.speakerOn = Boolean(window.MeshchatNextAndroid?.isTelephoneSpeakerOn?.());
        },
        toggle() {
            if (!window.MeshchatNextAndroid?.setTelephoneSpeaker(!this.speakerOn)) {
                ToastUtils.error(this.$t("call.failed_to_toggle_speaker"));
                return;
            }
            setTimeout(() => window.dispatchEvent(new Event("meshchatnext-call-route")), 200);
        },
    },
};
</script>
