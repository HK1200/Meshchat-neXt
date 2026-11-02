<template>
    <section class="space-y-3" aria-label="Repeater MediaMesh and terminal">
        <h3 class="font-semibold">MediaMesh · repeater Radio2</h3>
        <p class="text-sm text-sem-fg-muted">
            Support depends on the firmware build, not its version number. Check this repeater before changing its
            second radio.
        </p>
        <button class="secondary-chip" :disabled="blocked" @click="inspect">Check support / refresh</button>
        <p v-if="support === 'unsupported'" role="status">
            This firmware does not report compatible Radio2 settings. The terminal remains available for
            firmware-specific commands.
        </p>
        <template v-if="support === 'supported'">
            <p class="text-sm whitespace-pre-wrap">{{ report }}</p>
            <form class="space-y-3" @submit.prevent="apply">
                <label class="block"
                    >Mode<select v-model="mode" class="input-field block w-full" :disabled="blocked">
                        <option value="off">Off</option>
                        <option value="rx">Listen only</option>
                        <option value="rxtx">Listen and send</option>
                    </select></label
                >
                <template v-if="mode !== 'off'">
                    <label v-for="field in fields" :key="field.key" class="block"
                        >{{ field.label
                        }}<input
                            v-model="profile[field.key]"
                            type="number"
                            :step="field.step"
                            required
                            class="input-field block w-full"
                            :disabled="blocked"
                    /></label>
                    <button type="button" class="secondary-chip" :disabled="blocked" @click="preset">
                        Use 911.150 / BW250 / SF7 / CR4/5 preset
                    </button>
                    <p class="text-xs text-sem-fg-muted">
                        Choose your local group's profile. The preset is not applied until you save. Primary radio
                        settings are preserved; crossing is disabled. Enabling also asks compatible firmware to enable
                        its public #mediamesh forwarding region; existing default regions stay unchanged.
                    </p>
                </template>
                <label class="flex gap-2"
                    ><input v-model="confirmed" type="checkbox" :disabled="blocked" />Apply these settings to this
                    repeater. This may interrupt media traffic.</label
                >
                <button class="primary-chip" :disabled="blocked || !confirmed">Save and verify</button>
            </form>
        </template>
        <p v-if="message" role="status" class="text-sm whitespace-pre-wrap">{{ message }}</p>
        <details>
            <summary class="cursor-pointer font-semibold">Advanced terminal</summary>
            <p class="text-xs text-sem-fg-muted mt-2">
                One command at a time using your administrator login. Commands can change settings, reboot or erase the
                repeater. Available commands vary by firmware. No automatic retries or saved command history.
            </p>
            <form class="space-y-2 mt-2" @submit.prevent="run">
                <label class="block"
                    >Command<input
                        v-model="command"
                        class="input-field block w-full font-mono"
                        autocomplete="off"
                        autocapitalize="off"
                        spellcheck="false"
                        :disabled="blocked"
                /></label>
                <label class="flex gap-2"
                    ><input v-model="terminalConfirmed" type="checkbox" :disabled="blocked" />Send this command to this
                    repeater.</label
                >
                <button class="secondary-chip" :disabled="blocked || !command.trim() || !terminalConfirmed">
                    Send command
                </button>
            </form>
            <pre v-if="output" aria-label="Terminal response" class="whitespace-pre-wrap break-words text-sm mt-2">{{
                output
            }}</pre>
            <button v-if="output" type="button" class="secondary-chip" @click="output = ''">Clear response</button>
        </details>
    </section>
</template>
<script setup>
import { computed, onBeforeUnmount, ref } from "vue";
const props = defineProps({ request: { type: Function, required: true }, disabled: Boolean });
const pending = ref(false),
    support = ref("unknown"),
    report = ref(""),
    message = ref(""),
    output = ref(""),
    command = ref(""),
    confirmed = ref(false),
    terminalConfirmed = ref(false),
    mode = ref("off");
const profile = ref({ frequency: 911.15, bandwidth: 250, sf: 7, cr: 5 });
const fields = [
    { key: "frequency", label: "Frequency (MHz)", step: "0.001" },
    { key: "bandwidth", label: "Bandwidth (kHz)", step: "0.001" },
    { key: "sf", label: "Spreading factor", step: "1" },
    { key: "cr", label: "Coding rate (5–8)", step: "1" },
];
const blocked = computed(() => pending.value || props.disabled);
let alive = true;
onBeforeUnmount(() => {
    alive = false;
});
function preset() {
    profile.value = { frequency: 911.15, bandwidth: 250, sf: 7, cr: 5 };
    confirmed.value = false;
}
function decode(text) {
    if (/^> off(?:$|[ ;(])/.test(text)) return { mode: "off" };
    const match = /^> ([\d.]+),([\d.]+),(\d+),(\d+),(rx|rxtx),(\d+)(?:$|[ ;(])/.exec(text);
    if (!match) throw new Error("This firmware returned an unrecognized Radio2 profile; use its terminal reference.");
    return {
        mode: match[5],
        profile: {
            frequency: Number(match[1]),
            bandwidth: Number(match[2]),
            sf: Number(match[3]),
            cr: Number(match[4]),
        },
    };
}
async function ask(action, value = "", confirm = false) {
    if (!alive) throw new Error("Repeater session changed.");
    const text = await props.request(action, value, confirm);
    if (!alive) throw new Error("Repeater session changed.");
    return text;
}
async function read() {
    const text = await ask("radio2");
    if (/unknown|unsupported|not supported|unrecognized command/i.test(text)) {
        support.value = "unsupported";
        return null;
    }
    const parsed = decode(text);
    const crossing = await ask("radio2-cross");
    if (!/^> (off|on)$/.test(crossing))
        throw new Error("This firmware does not report compatible MediaMesh routing controls.");
    support.value = "supported";
    mode.value = parsed.mode;
    if (parsed.profile) profile.value = parsed.profile;
    report.value = `${text}\nCrossing: ${crossing}`;
    return { ...parsed, crossing };
}
async function inspect() {
    if (blocked.value) return;
    pending.value = true;
    message.value = "";
    support.value = "unknown";
    confirmed.value = false;
    try {
        await read();
    } catch (error) {
        if (alive) message.value = error.message;
    } finally {
        pending.value = false;
    }
}
async function apply() {
    if (blocked.value || !confirmed.value || support.value !== "supported") return;
    const target = { ...profile.value },
        targetMode = mode.value;
    pending.value = true;
    confirmed.value = false;
    message.value = "";
    try {
        const primary = await ask("radio");
        if (targetMode !== "off") {
            if (!Object.values(target).every((v) => Number.isFinite(Number(v))))
                throw new Error("Enter numeric profile values.");
            if (
                Number(target.frequency) < 150 ||
                Number(target.frequency) > 2500 ||
                Number(target.bandwidth) < 7 ||
                Number(target.bandwidth) > 500 ||
                !Number.isInteger(Number(target.sf)) ||
                Number(target.sf) < 5 ||
                Number(target.sf) > 12 ||
                !Number.isInteger(Number(target.cr)) ||
                Number(target.cr) < 5 ||
                Number(target.cr) > 8
            )
                throw new Error("Profile values are outside the supported ranges; no changes sent.");
            const primaryFrequency = Number(/^>\s*([\d.]+)/.exec(primary)?.[1]);
            if (!Number.isFinite(primaryFrequency))
                throw new Error("Primary profile could not be read; no changes sent.");
            if (Number(target.frequency) === primaryFrequency)
                throw new Error("Radio2 needs a different frequency from the primary radio.");
            for (const [action, value] of [
                ["set-radio2-cross", "off"],
                ["set-radio2-preset", Number(target.bandwidth) === 125 ? "mediamesh-range" : "mediamesh"],
            ]) {
                if ((await ask(action, value, true)).trim() !== "OK")
                    throw new Error("Firmware rejected a MediaMesh setting; inspect before continuing.");
            }
        }
        const value =
            targetMode === "off"
                ? "off"
                : `${target.frequency},${target.bandwidth},${target.sf},${target.cr},${targetMode}`;
        if ((await ask("set-radio2", value, true)).trim() !== "OK")
            throw new Error("Firmware did not confirm the Radio2 change.");
        const result = await read();
        const primaryAfter = await ask("radio");
        if (
            !result ||
            result.mode !== targetMode ||
            primaryAfter !== primary ||
            (targetMode !== "off" &&
                (Object.keys(target).some((k) => Number(target[k]) !== result.profile[k]) ||
                    result.crossing !== "> off"))
        )
            throw new Error("Readback differs from the requested settings. Inspect this repeater before continuing.");
        message.value = "Radio2 settings verified. Primary profile unchanged.";
    } catch (error) {
        if (alive)
            message.value = `${error.message} No automatic retry was sent; some settings may already have changed.`;
    } finally {
        pending.value = false;
    }
}
async function run() {
    if (blocked.value || !terminalConfirmed.value || !command.value.trim()) return;
    const text = command.value;
    command.value = "";
    terminalConfirmed.value = false;
    pending.value = true;
    support.value = "unknown";
    confirmed.value = false;
    try {
        const reply = await ask("terminal", text, true);
        if (alive) output.value = reply || "Empty response.";
    } catch (error) {
        if (alive) output.value = error.message;
    } finally {
        pending.value = false;
    }
}
</script>
