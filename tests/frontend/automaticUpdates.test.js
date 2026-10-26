import { describe, it, expect, vi, afterEach } from "vitest";
vi.mock("../../meshchatnext/src/frontend/js/api/update.js", () => ({ checkUpdate: vi.fn() }));
import { checkUpdate } from "../../meshchatnext/src/frontend/js/api/update.js";
import { startAutomaticUpdates } from "../../meshchatnext/src/frontend/js/automaticUpdates.js";
afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
});
describe("automatic signed update notifications", () => {
    it("checks after launch, deduplicates alerts and stops cleanly", async () => {
        vi.useFakeTimers();
        checkUpdate.mockResolvedValue({
            data: { enabled: true, update_available: true, manifest: { version: "0.2.0" } },
        });
        const notify = vi.fn();
        const stop = startAutomaticUpdates(notify, { intervalMs: 30000 });
        await vi.advanceTimersByTimeAsync(15000);
        expect(notify).toHaveBeenCalledWith("0.2.0");
        await vi.advanceTimersByTimeAsync(60000);
        expect(notify).toHaveBeenCalledTimes(1);
        stop();
        const calls = checkUpdate.mock.calls.length;
        await vi.advanceTimersByTimeAsync(60000);
        expect(checkUpdate).toHaveBeenCalledTimes(calls);
    });
    it("quietly tolerates offline checks and disabled updates", async () => {
        vi.useFakeTimers();
        checkUpdate.mockRejectedValueOnce(new Error("offline")).mockResolvedValue({ data: { enabled: false } });
        const notify = vi.fn();
        const stop = startAutomaticUpdates(notify, { intervalMs: 30000 });
        await vi.advanceTimersByTimeAsync(45000);
        expect(notify).not.toHaveBeenCalled();
        stop();
    });
});
