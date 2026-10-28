<template>
    <section
        v-if="snapshot.radios"
        class="space-y-3 rounded-lg border border-sem-border p-3"
        aria-label="MeshCore radios"
    >
        <label class="block text-sm"
            >Inbox view
            <select
                class="input-field"
                aria-label="MeshCore inbox view"
                :value="snapshot.inbox_mode"
                :disabled="disabled || busy"
                @change="run('radio-configure', { view: $event.target.value })"
            >
                <option value="combined">Combined inbox with radio labels</option>
                <option value="separate">Separate radio views</option>
            </select>
        </label>
        <p class="text-xs text-sem-fg-muted">
            Every enabled radio receives and reconnects independently in either view. Radio messages are not forwarded
            between radios.
        </p>
        <p v-if="snapshot.radios_error" role="alert" class="text-sm text-sem-danger">{{ snapshot.radios_error }}</p>
        <article v-for="radio in snapshot.radios" :key="radio.id" class="space-y-2 border-t border-sem-border pt-3">
            <div class="flex flex-wrap gap-2 items-center">
                <strong class="text-sm">{{ radio.label }}</strong>
                <span class="text-xs text-sem-fg-muted">{{
                    radio.connected
                        ? "Connected"
                        : radio.state === "identity_changed"
                          ? "Identity check needs attention"
                          : radio.auto_reconnect
                            ? "Reconnecting when available"
                            : "Disconnected"
                }}</span>
                <span v-if="radio.id === snapshot.radio_id" class="text-xs text-sem-accent">Selected</span>
            </div>
            <p v-if="radio.connection" class="text-xs text-sem-fg-muted break-all">
                {{ radio.connection.kind === "ble" ? "Bluetooth LE" : "USB" }} · {{ radio.connection.target }}
            </p>
            <div class="flex flex-wrap gap-2">
                <button
                    type="button"
                    class="secondary-chip"
                    :disabled="disabled || busy || radio.id === snapshot.radio_id"
                    @click="run('radio-configure', { active: radio.id })"
                >
                    Use this radio
                </button>
                <button
                    v-if="radio.connection"
                    type="button"
                    class="secondary-chip"
                    :disabled="disabled || busy"
                    @click="run('radio-enabled', { radio_id: radio.id, enabled: !radio.auto_reconnect })"
                >
                    {{ radio.auto_reconnect ? "Disable radio" : "Enable and reconnect" }}
                </button>
                <button
                    v-if="radio.id !== 'default'"
                    type="button"
                    class="secondary-chip"
                    :disabled="disabled || busy"
                    @click="run('radio-remove', { radio_id: radio.id })"
                >
                    Remove saved radio
                </button>
            </div>
            <details>
                <summary class="text-xs text-sem-fg-muted cursor-pointer">Rename radio</summary>
                <form
                    class="flex gap-2"
                    @submit.prevent="
                        run('radio-configure', { radio_id: radio.id, label: names[radio.id] || radio.label })
                    "
                >
                    <input
                        v-model="names[radio.id]"
                        class="input-field min-w-0"
                        :aria-label="`Name for ${radio.label}`"
                        :placeholder="radio.label"
                        maxlength="80"
                        :disabled="disabled || busy"
                    />
                    <button class="secondary-chip" :disabled="disabled || busy || !names[radio.id]?.trim()">
                        Rename
                    </button>
                </form>
            </details>
        </article>
        <details class="border-t border-sem-border pt-3">
            <summary class="text-sm font-medium cursor-pointer">Add another MeshCore radio</summary>
            <form data-add-meshcore-radio class="space-y-3 pt-3" @submit.prevent="add">
                <label class="block text-sm"
                    >Radio name<input
                        v-model="label"
                        class="input-field"
                        maxlength="80"
                        required
                        :disabled="disabled || busy"
                /></label>
                <label class="block text-sm"
                    >Connection<select
                        v-model="kind"
                        class="input-field"
                        :disabled="disabled || busy"
                        @change="
                            target = '';
                            devices = [];
                        "
                    >
                        <option value="ble">Bluetooth LE</option>
                        <option value="usb">USB</option>
                    </select></label
                >
                <button type="button" class="secondary-chip" :disabled="disabled || busy" @click="discover">
                    {{ kind === "ble" ? "Find Bluetooth radios" : "Find USB radios" }}
                </button>
                <label v-if="devices.length" class="block text-sm"
                    >Choose radio<select v-model="target" class="input-field" :disabled="disabled || busy">
                        <option disabled value="">Choose your MeshCore companion</option>
                        <option
                            v-for="device in devices"
                            :key="device.address || device.path"
                            :value="device.address || device.path"
                        >
                            {{ device.name }} · {{ device.address || device.path }}
                        </option>
                    </select></label
                >
                <label class="block text-sm"
                    >{{ kind === "ble" ? "Bluetooth address" : "USB device path"
                    }}<input
                        v-model="target"
                        class="input-field"
                        required
                        :disabled="disabled || busy"
                        autocomplete="off"
                /></label>
                <p class="text-xs text-sem-fg-muted">
                    Select only a MeshCore companion. Each enabled radio reconnects when available. Removing a saved
                    radio keeps its messages.
                </p>
                <button class="primary-chip" :disabled="disabled || busy || !target.trim() || !label.trim()">
                    Save and connect radio
                </button>
            </form>
        </details>
        <p v-if="problem" role="alert" class="text-sm text-sem-danger">{{ problem }}</p>
    </section>
</template>
<script setup>
import { ref } from "vue";
import { apiPath } from "../../js/constants";
const props = defineProps({
    snapshot: { type: Object, required: true },
    action: { type: Function, required: true },
    disabled: Boolean,
});
const emit = defineEmits(["busy"]);
const names = ref({}),
    label = ref(""),
    kind = ref("ble"),
    target = ref(""),
    devices = ref([]),
    busy = ref(false),
    problem = ref("");
async function run(name, body) {
    busy.value = true;
    emit("busy", true);
    problem.value = "";
    try {
        const connection =
            name === "radio-add"
                ? body
                : name === "radio-enabled" && body.enabled
                  ? props.snapshot.radios.find((radio) => radio.id === body.radio_id)?.connection
                  : null;
        if (connection?.kind === "usb" && props.snapshot.radio_platform === "android") {
            const permission = await window.api.post(apiPath("/meshcore/usb-permission"), { path: connection.target });
            if (!permission.data.result?.granted) {
                problem.value = "Allow USB access in Android, then try again.";
                return;
            }
        }
        await props.action(name, body);
    } catch (error) {
        problem.value =
            error?.response?.data?.message || "Could not change the saved radios. Check their connection status.";
    } finally {
        busy.value = false;
        emit("busy", false);
    }
}
async function discover() {
    busy.value = true;
    emit("busy", true);
    problem.value = "";
    try {
        devices.value =
            (await window.api.get(apiPath(`/meshcore/${kind.value === "ble" ? "bluetooth-devices" : "usb-devices"}`)))
                .data.result || [];
    } catch {
        problem.value = "Could not list radios. Check Bluetooth or USB access.";
    } finally {
        busy.value = false;
        emit("busy", false);
    }
}
async function add() {
    await run("radio-add", {
        kind: kind.value,
        target: target.value.trim(),
        label: label.value.trim(),
        receive: true,
        auto_reconnect: true,
    });
}
</script>
