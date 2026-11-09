import { computed, onBeforeUnmount, ref, watch } from "vue";

const encoder = new TextEncoder();
const CONFIRMATION_TIMEOUT_MS = 30_000;
// The standard companion omits RX-log frames larger than 173 RF bytes.
const RX_LOG_PACKET_BYTES = 173;
const SCOPED_HEADER_BYTES = 6;
const MAX_PATH_BYTES = 64;
const DM_ENVELOPE_BYTES = 4;
const AES_BLOCK_BYTES = 16;
const TEXT_HEADER_BYTES = 5;
const repeatPlaintextBytes =
    Math.floor((RX_LOG_PACKET_BYTES - SCOPED_HEADER_BYTES - MAX_PATH_BYTES - DM_ENVELOPE_BYTES) / AES_BLOCK_BYTES) *
    AES_BLOCK_BYTES;
export const REPEAT_TEXT_BYTES = repeatPlaintextBytes - TEXT_HEADER_BYTES;

export function meshCoreChannelTextBytes(profileName) {
    return Math.max(0, REPEAT_TEXT_BYTES - meshCoreTextBytes(profileName) - 2);
}

export function meshCoreTextBytes(text) {
    return encoder.encode(text).length;
}

export function splitMeshCoreText(text, maximum) {
    if (maximum <= 0 || !text) return [];
    if (meshCoreTextBytes(text) <= maximum) return [text];

    const parts = [];
    let part = "",
        size = 0;
    for (const character of text) {
        const bytes = meshCoreTextBytes(character);
        if (bytes > maximum) return [];
        if (size + bytes > maximum) {
            parts.push(part);
            part = "";
            size = 0;
        }
        part += character;
        size += bytes;
    }
    if (part) parts.push(part);
    return parts;
}

function confirmed(row, channel) {
    return (
        (!channel && row?.state === "delivered") ||
        (row?.heard_repeats > 0 && (channel || row?.sent_route !== "direct"))
    );
}

function waitForConfirmation(history, id, channel, signal) {
    if (signal.aborted) return Promise.resolve(false);
    return new Promise((resolve) => {
        const read = () =>
            confirmed(
                history().find((row) => row.id === id && row.direction === "out"),
                channel
            );
        const stop = watch(read, (ready) => {
            if (ready) finish(true);
        });
        const timer = setTimeout(() => finish(false), CONFIRMATION_TIMEOUT_MS);
        const abort = () => finish(false);
        function finish(value) {
            stop();
            clearTimeout(timer);
            signal.removeEventListener("abort", abort);
            resolve(value);
        }
        signal.addEventListener("abort", abort, { once: true });
        if (read()) finish(true);
    });
}

export function useMeshCoreTextSend({ draft, busy, maximum, ready, context, history, submit, channel = false }) {
    const bytes = computed(() => meshCoreTextBytes(draft.value));
    const parts = computed(() => splitMeshCoreText(draft.value, maximum()));
    const status = ref("");
    let pending = null,
        sequence = null;
    const canSend = computed(
        () =>
            ready() &&
            !busy.value &&
            Boolean(draft.value.trim()) &&
            !draft.value.includes("\0") &&
            parts.value.length > 0
    );

    function reset() {
        sequence?.abort();
        pending = null;
        status.value = "";
    }
    watch(context, reset, { flush: "sync" });
    onBeforeUnmount(reset);

    async function send() {
        if (!canSend.value) return;
        const frames = parts.value;
        const controller = new AbortController();
        sequence = controller;
        busy.value = true;
        status.value = "";

        try {
            for (const [index, text] of frames.entries()) {
                if (controller.signal.aborted) return;
                if (!ready() || meshCoreTextBytes(text) > maximum()) {
                    status.value = "MeshCore settings changed. The remaining text is still in your draft.";
                    return;
                }
                if (pending?.text !== text) pending = { text, request_id: crypto.randomUUID() };
                if (frames.length > 1) status.value = `Sending part ${index + 1} of ${frames.length}…`;
                const result = await submit(pending);
                if (controller.signal.aborted) return;
                if (result.state === "rejected") {
                    pending = null;
                    status.value = "The radio rejected this message. Your draft is still here.";
                    return;
                }
                const accepted = channel
                    ? result.state === "submitted"
                    : ["accepted", "unconfirmed", "delivered"].includes(result.state);
                if (!accepted) {
                    status.value = "The send result is uncertain. Check the conversation before trying again.";
                    return;
                }

                const id = pending.request_id;
                pending = null;
                draft.value = draft.value.slice(text.length);
                if (index === frames.length - 1) {
                    if (frames.length > 1) status.value = `Submitted all ${frames.length} parts to the radio.`;
                    return;
                }
                status.value = `Waiting for confirmation of part ${index + 1} of ${frames.length}…`;
                const proceed =
                    confirmed(result, channel) || (await waitForConfirmation(history, id, channel, controller.signal));
                if (controller.signal.aborted) return;
                if (!proceed) {
                    status.value = "No confirmation heard. The remaining text is still in your draft.";
                    return;
                }
            }
        } catch {
            if (!controller.signal.aborted)
                status.value = "MeshCore did not confirm the send. Your draft is still here.";
        } finally {
            busy.value = false;
            sequence = null;
        }
    }
    return { bytes, parts, status, canSend, send };
}
