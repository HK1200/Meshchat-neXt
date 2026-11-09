// SPDX-License-Identifier: 0BSD

import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { repeatPrivateLocation } from "@/js/timedPrivateLocation";

const origin = { latitude: 1, longitude: 2, accuracy: 8 };

beforeEach(() => {
    vi.useFakeTimers();
    vi.spyOn(document, "hidden", "get").mockReturnValue(false);
});
afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
});

function share(options = {}) {
    const sendFix = vi.fn();
    const onStop = vi.fn();
    const stop = repeatPrivateLocation({
        deadline: Date.now() + 900_000,
        firstFix: origin,
        getFix: async () => origin,
        isCurrent: () => true,
        sendFix,
        onStop,
        ...options,
    });
    return { sendFix, onStop, stop };
}

it("checks in after five minutes when stationary and stops at the deadline", async () => {
    const { sendFix, onStop } = share();
    await vi.advanceTimersByTimeAsync(299_999);
    expect(sendFix).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(sendFix).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(600_000);
    expect(sendFix).toHaveBeenCalledTimes(2);
    expect(onStop).toHaveBeenCalledWith("expired");
});

it("sends a new fix after moving and ignores jitter around that fix", async () => {
    const fix = { ...origin, latitude: 1.001 };
    const { sendFix, stop } = share({ getFix: async () => fix });
    await vi.advanceTimersByTimeAsync(120_000);
    expect(sendFix).toHaveBeenCalledExactlyOnceWith(fix);
    stop();
});

it("stopping invalidates a location request already in flight", async () => {
    let completeFix;
    const { sendFix, stop } = share({
        getFix: () => new Promise((resolve) => { completeFix = resolve; }),
    });
    await vi.advanceTimersByTimeAsync(60_000);
    stop();
    completeFix({ ...origin, latitude: 2 });
    await vi.advanceTimersByTimeAsync(60_000);
    expect(sendFix).not.toHaveBeenCalled();
});

it("backgrounding the app stops sharing", async () => {
    const { sendFix, onStop } = share();
    vi.mocked(Object.getOwnPropertyDescriptor(document, "hidden").get).mockReturnValue(true);
    document.dispatchEvent(new Event("visibilitychange"));
    await vi.advanceTimersByTimeAsync(300_000);
    expect(sendFix).not.toHaveBeenCalled();
    expect(onStop).toHaveBeenCalledWith("stopped");
});
