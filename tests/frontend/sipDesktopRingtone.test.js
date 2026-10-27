import { expect, it, vi } from "vitest";
import { createSipDesktopRingtone } from "../../meshchatnext/src/frontend/js/sipDesktopRingtone";
it("uses one custom ringtone and stops it immediately", async () => {
    const players = [];
    class Audio { constructor(url) { this.url = url; this.play = vi.fn().mockResolvedValue(); this.pause = vi.fn(); players.push(this); } }
    const ring = createSipDesktopRingtone({ Audio, getStatus: async () => ({ has_custom_ringtone: true, id: 12, volume: .4 }) });
    await ring.start("one"); await ring.start("one");
    expect(players).toHaveLength(1);
    expect(players[0].loop).toBe(true);
    expect(players[0].volume).toBe(.4);
    ring.stop();
    expect(players[0].pause).toHaveBeenCalledOnce();
});
it("never starts a ringtone after the call has already ended", async () => {
    let resolve;
    const Audio = vi.fn();
    const ring = createSipDesktopRingtone({ Audio, getStatus: () => new Promise(r => { resolve = r; }) });
    const pending = ring.start("one");
    ring.stop();
    resolve({ has_custom_ringtone: true, id: 12 });
    await pending;
    expect(Audio).not.toHaveBeenCalled();
});
it("repeats a built-in tone and releases its timer and audio context", async () => {
    const oscillator = { frequency: {}, connect: vi.fn(), start: vi.fn(), stop: vi.fn() };
    const gain = { gain: { setValueAtTime: vi.fn(), linearRampToValueAtTime: vi.fn() }, connect: vi.fn() };
    const contexts = [];
    class AudioContext { constructor() { this.currentTime = 0; this.createOscillator = vi.fn(() => oscillator); this.createGain = vi.fn(() => gain); this.resume = vi.fn().mockResolvedValue(); this.close = vi.fn().mockResolvedValue(); contexts.push(this); } }
    const schedule = vi.fn(() => 7), clear = vi.fn();
    const ring = createSipDesktopRingtone({ AudioContext, getStatus: async () => ({}), setInterval: schedule, clearInterval: clear });
    await ring.start("one");
    expect(contexts[0].createOscillator).toHaveBeenCalledTimes(2);
    expect(schedule).toHaveBeenCalledWith(expect.any(Function), 5000);
    ring.stop();
    expect(clear).toHaveBeenCalledWith(7);
    expect(contexts[0].close).toHaveBeenCalledOnce();
});
