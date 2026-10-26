<!-- SPDX-License-Identifier: 0BSD -->
<template>
    <div class="flex-1 overflow-y-auto bg-sem-canvas text-sem-fg p-4 md:p-6">
        <div class="max-w-3xl mx-auto">
            <h1 class="text-2xl font-bold">SIP settings</h1>
            <p class="text-sm text-sem-fg-muted mt-2">
                Manage your extensions, saved passwords and connection preferences.
            </p>
            <SipPhone mode="settings" />
        </div>
    </div>
</template>
<script setup>
import SipPhone from "./SipPhone.vue";
</script>
