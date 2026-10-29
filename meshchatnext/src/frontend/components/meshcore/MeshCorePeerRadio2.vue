<template>
    <dl class="space-y-1 text-sm" aria-label="Peer Radio2 report">
        <div v-for="row in rows" :key="row.label">
            <dt class="text-sem-fg-muted">{{ row.label }}</dt>
            <dd>{{ row.value }}</dd>
        </div>
    </dl>
</template>
<script setup>
import { computed } from "vue";
import { peerRadio2Rows } from "../../js/meshcorePeerRadio2";
const props = defineProps({ report: { type: Object, default: null } });
const rows = computed(() => peerRadio2Rows(props.report));
</script>
