<!-- SPDX-License-Identifier: 0BSD -->
<template>
    <AppModal
        :model-value="Boolean(form)"
        :title="title || (form?.id ? 'Edit SIP contact' : 'Add SIP contact')"
        body-class="overflow-y-auto"
        show-close
        @update:model-value="!$event && emit('close')"
    >
        <form v-if="form" class="p-4 space-y-3" @submit.prevent="save">
            <label class="block text-sm"
                >Name<input
                    v-model="form.name"
                    class="rounded-lg border border-sem-border bg-sem-surface px-3 py-2 text-sem-fg focus:outline-none focus:ring-1 focus:ring-sem-accent block w-full"
                    maxlength="100"
                    required
            /></label>
            <fieldset
                v-for="(number, index) in form.numbers"
                :key="index"
                class="border border-sem-border rounded-lg p-2 space-y-2"
            >
                <legend class="text-sm">Number {{ index + 1 }}</legend>
                <label class="block text-sm"
                    >Type<select
                        v-model="number.label"
                        class="input-field block w-full"
                        :aria-label="`Number ${index + 1} type`"
                    >
                        <option v-for="label in labels" :key="label">{{ label }}</option>
                    </select></label
                >
                <label class="block text-sm"
                    >SIP extension or address<input
                        v-model="number.address"
                        class="input-field block w-full"
                        :aria-label="`Number ${index + 1} address`"
                        maxlength="320"
                        placeholder="Extension or sip:user@server"
                        required
                /></label>
                <button
                    type="button"
                    class="secondary-chip"
                    :disabled="form.numbers.length === 1"
                    :aria-label="`Remove number ${index + 1}`"
                    @click="form.numbers.splice(index, 1)"
                >
                    Remove number
                </button>
            </fieldset>
            <button
                type="button"
                class="secondary-chip"
                :disabled="form.numbers.length >= 12"
                @click="form.numbers.push({ label: 'Other', address: '' })"
            >
                Add another number
            </button>
            <p v-if="error" role="alert" class="text-sem-danger text-sm">{{ error }}</p>
            <div class="flex gap-2 flex-wrap">
                <button class="primary-chip" type="submit">Save contact</button
                ><button class="secondary-chip" type="button" @click="emit('close')">Cancel</button
                ><button
                    v-if="form.id && allowDelete"
                    class="secondary-chip text-sem-danger"
                    type="button"
                    @click="remove"
                >
                    Delete SIP contact
                </button>
            </div>
        </form>
    </AppModal>
</template>

<script setup>
import { ref, watch } from "vue";
import AppModal from "../AppModal.vue";
import { sipContactNumbers, saveSipContact, deleteSipContact } from "../../js/sip";
const props = defineProps({
    contact: { type: Object, default: null },
    title: { type: String, default: "" },
    allowDelete: { type: Boolean, default: true },
});
const emit = defineEmits(["close", "saved"]);
const labels = ["Home", "Office", "Mobile", "Other"];
const form = ref(null),
    error = ref("");
watch(
    () => props.contact,
    (contact) => {
        error.value = "";
        form.value = contact ? { ...contact, numbers: sipContactNumbers(contact) } : null;
    },
    { immediate: true }
);
function save() {
    try {
        const row = saveSipContact(form.value);
        emit("saved", row);
    } catch (e) {
        error.value = e.message;
    }
}
function remove() {
    try {
        deleteSipContact(form.value.id);
        emit("saved", null);
    } catch (e) {
        error.value = e.message;
    }
}
</script>
