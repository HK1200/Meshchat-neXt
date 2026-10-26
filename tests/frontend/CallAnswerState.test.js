import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import CallPage from "@/components/call/CallPage.vue";
import ToastUtils from "@/js/ToastUtils";
vi.mock("@/js/stores/networkStore", () => ({ useNetworkStore: () => ({ liveTransportReady: true }) }));
const ringing = { hash: "same-call", is_incoming: true, status: 4 };
const connected = { ...ringing, status: 6 };
let ctx;
beforeEach(() => {
    window.api = { post: vi.fn().mockResolvedValue({}) };
    vi.spyOn(ToastUtils, "error").mockImplementation(() => {});
    ctx = {
        activeCall: ringing,
        answeringCall: false,
        webAudioBridgeEnabled: false,
        getStatus: vi.fn().mockResolvedValue(ringing),
        $t: (key) => key,
    };
});
afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
});
describe("incoming call answer state", () => {
    it("does not answer again when the banner already connected the call", async () => {
        ctx.getStatus.mockResolvedValue(connected);
        await CallPage.methods.answerCall.call(ctx);
        expect(window.api.post).not.toHaveBeenCalled();
        expect(ToastUtils.error).not.toHaveBeenCalled();
        expect(ctx.answeringCall).toBe(false);
    });
    it("suppresses a rejected duplicate only after confirming the same call connected", async () => {
        ctx.getStatus.mockResolvedValueOnce(ringing).mockResolvedValueOnce(connected);
        window.api.post.mockRejectedValue(new Error("already answered"));
        await CallPage.methods.answerCall.call(ctx);
        expect(window.api.post).toHaveBeenCalledTimes(1);
        expect(ToastUtils.error).not.toHaveBeenCalled();
    });
    it.each([ringing, null, undefined, { ...connected, hash: "another-call" }])(
        "keeps genuine answer failures visible (%j)",
        async (state) => {
            ctx.getStatus.mockResolvedValueOnce(ringing).mockResolvedValueOnce(state);
            window.api.post.mockRejectedValue(new Error("failed"));
            await CallPage.methods.answerCall.call(ctx);
            expect(ToastUtils.error).toHaveBeenCalledWith("call.failed_to_answer_call");
            expect(ctx.answeringCall).toBe(false);
        }
    );
    it("answers a ringing call once and refreshes afterward", async () => {
        await CallPage.methods.answerCall.call(ctx);
        expect(window.api.post).toHaveBeenCalledTimes(1);
        expect(ctx.getStatus).toHaveBeenCalledTimes(2);
    });
    it("ignores repeated taps while an answer is pending", async () => {
        let resolve;
        ctx.getStatus.mockReturnValueOnce(
            new Promise((done) => {
                resolve = done;
            })
        );
        const pending = CallPage.methods.answerCall.call(ctx);
        await CallPage.methods.answerCall.call(ctx);
        resolve(ringing);
        await pending;
        expect(window.api.post).toHaveBeenCalledTimes(1);
    });
    it("polls ringing state each second even with a connected live transport", () => {
        vi.useFakeTimers();
        Object.assign(ctx, { getVoicemailStatus: vi.fn(), getRingtoneStatus: vi.fn() });
        CallPage.methods.startStatusPollInterval.call(ctx);
        vi.advanceTimersByTime(1000);
        expect(ctx.getStatus).toHaveBeenCalledTimes(1);
        clearInterval(ctx.statusInterval);
    });
});
