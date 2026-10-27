import { expect, it, vi } from "vitest";
import { createSipCallNotifications } from "../../electron/sipCallNotifications.js";
function setup() {
    const notes = [];
    const window = { show: vi.fn(), focus: vi.fn(), webContents: { send: vi.fn(), setBackgroundThrottling: vi.fn() } };
    class Notification {
        constructor(options) { this.options = options; this.handlers = {}; this.close = vi.fn(); this.show = vi.fn(); notes.push(this); }
        on(name, handler) { this.handlers[name] = handler; }
    }
    return { notes, window, update: createSipCallNotifications({ Notification, getWindow: () => window }) };
}
const call = { enabled: true, incoming: true, callId: "ab".repeat(16), peer: "sip:1234@example.test" };
it("deduplicates incoming calls and routes explicit answer actions to the app", () => {
    const { notes, window, update } = setup();
    update(call); update(call);
    expect(notes).toHaveLength(1);
    expect(notes[0].options.title).toBe("SIP · Incoming call");
    notes[0].handlers.action({}, 0);
    expect(window.webContents.send).toHaveBeenCalledWith("open-sip-call", { action: "answer", callId: call.callId });
    expect(window.focus).toHaveBeenCalledOnce();
});
it("clears completed alerts and ignores stale notification actions", () => {
    const { notes, window, update } = setup();
    update(call);
    update({ enabled: true, incoming: false });
    expect(notes[0].close).toHaveBeenCalledOnce();
    notes[0].handlers.click();
    expect(window.webContents.send).not.toHaveBeenCalled();
});
it("respects DND and restores background throttling when disabled", () => {
    const { notes, window, update } = setup();
    update({ ...call, dnd: true });
    expect(notes).toHaveLength(0);
    update({ enabled: false, incoming: false });
    expect(window.webContents.setBackgroundThrottling).toHaveBeenLastCalledWith(true);
});
it("rejects arbitrary routes or control characters in caller data", () => {
    const { notes, update } = setup();
    expect(update({ ...call, callId: "https://untrusted.test" })).toBe(false);
    expect(update({ ...call, peer: "bad\ncaller" })).toBe(false);
    expect(notes).toHaveLength(0);
});

it("tracks active call suspension separately from OS alert visibility", () => {
    const active = vi.fn();
    const update = createSipCallNotifications({ Notification: class {}, getWindow: () => null, setCallActive: active });
    update({ enabled: true, incoming: false, active: true });
    expect(active).toHaveBeenLastCalledWith(true);
    update({ enabled: true, incoming: false, active: false });
    expect(active).toHaveBeenLastCalledWith(false);
    update({ enabled: true, incoming: true, active: true, dnd: true });
    expect(active).toHaveBeenLastCalledWith(true);
    update({ enabled: false, incoming: false });
    expect(active).toHaveBeenLastCalledWith(false);
});
