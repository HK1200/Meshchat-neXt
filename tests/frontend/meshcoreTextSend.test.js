import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { nextTick, ref } from "vue";
import {
    REPEAT_TEXT_BYTES,
    meshCoreChannelTextBytes,
    meshCoreTextBytes,
    splitMeshCoreText,
    useMeshCoreTextSend,
} from "@/js/meshcoreTextSend";

let wrapper;

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
    wrapper?.unmount();
    wrapper = null;
    vi.useRealTimers();
});

function composer({ text = "abcdefghij", channel = false } = {}) {
    const draft = ref(text);
    const history = ref([]);
    const context = ref("current");
    const submit = vi.fn().mockResolvedValue({ state: channel ? "submitted" : "accepted" });
    let sender;
    wrapper = mount({
        setup() {
            sender = useMeshCoreTextSend({
                draft,
                busy: ref(false),
                maximum: () => 4,
                ready: () => true,
                context: () => context.value,
                history: () => history.value,
                submit,
                channel,
            });
            return () => null;
        },
    });
    return { ...sender, draft, submit, history, context };
}

it("splits at UTF-8 boundaries without losing text", () => {
    const text = "é🙂xx日本語";
    const parts = splitMeshCoreText(text, 6);
    expect(parts.join("")).toBe(text);
    expect(parts.every((part) => meshCoreTextBytes(part) <= 6)).toBe(true);
    expect(splitMeshCoreText("🙂", 3)).toEqual([]);
});

it("budgets encrypted text for scoped flood and a full-width standard path", () => {
    const scopedHeader = 6,
        pathBytes = 64,
        directEnvelope = 4,
        channelEnvelope = 3;
    const wireSize = (textBytes, envelopeBytes) =>
        scopedHeader + pathBytes + envelopeBytes + 16 * Math.ceil((5 + textBytes) / 16);
    expect(wireSize(REPEAT_TEXT_BYTES, directEnvelope)).toBeLessThanOrEqual(173);
    expect(wireSize(REPEAT_TEXT_BYTES + 1, directEnvelope)).toBeGreaterThan(173);
    expect(splitMeshCoreText("x".repeat(160), REPEAT_TEXT_BYTES).map(meshCoreTextBytes)).toEqual([91, 69]);
    const name = "Radio 🦊";
    const channelBytes = meshCoreChannelTextBytes(name);
    expect(wireSize(channelBytes + meshCoreTextBytes(name) + 2, channelEnvelope)).toBeLessThanOrEqual(173);
});

it("waits for each channel part's own radio repeat", async () => {
    const c = composer({ channel: true });
    const sending = c.send();
    await flushPromises();
    expect(c.submit.mock.calls.map(([frame]) => frame.text)).toEqual(["abcd"]);
    const first = c.submit.mock.calls[0][0].request_id;
    c.history.value = [{ id: first, direction: "out", state: "submitted", heard_repeats: 0 }];
    await nextTick();
    expect(c.submit).toHaveBeenCalledTimes(1);
    c.history.value[0].heard_repeats = 1;
    await flushPromises();
    expect(c.submit.mock.calls.map(([frame]) => frame.text)).toEqual(["abcd", "efgh"]);
    const second = c.submit.mock.calls[1][0].request_id;
    c.history.value.push({ id: second, direction: "out", state: "submitted", heard_repeats: 1 });
    await sending;
    expect(c.submit.mock.calls.map(([frame]) => frame.text)).toEqual(["abcd", "efgh", "ij"]);
    expect(new Set(c.submit.mock.calls.map(([frame]) => frame.request_id)).size).toBe(3);
    expect(c.draft.value).toBe("");
});

it("allows a direct delivery acknowledgment and keeps unsent text on timeout", async () => {
    const c = composer();
    const sending = c.send();
    await flushPromises();
    const first = c.submit.mock.calls[0][0].request_id;
    c.history.value = [{ id: first, direction: "out", state: "delivered" }];
    await flushPromises();
    expect(c.submit).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(30_000);
    await sending;
    expect(c.submit).toHaveBeenCalledTimes(2);
    expect(c.draft.value).toBe("ij");
    expect(c.status.value).toContain("No confirmation");
});

it("keeps an uncertain frame and its request ID for a manual retry", async () => {
    const c = composer({ text: "abcd" });
    c.submit.mockRejectedValueOnce(new Error("Response lost"));
    await c.send();
    expect(c.draft.value).toBe("abcd");
    await c.send();
    expect(c.submit.mock.calls[0][0]).toEqual(c.submit.mock.calls[1][0]);
    expect(c.draft.value).toBe("");
});

it("stops a waiting sequence when the chat or radio changes", async () => {
    const c = composer();
    const sending = c.send();
    await flushPromises();
    c.context.value = "different";
    await sending;
    expect(c.submit).toHaveBeenCalledTimes(1);
});
