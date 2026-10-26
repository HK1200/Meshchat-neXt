import { mount, flushPromises } from "@vue/test-utils";
import { ref, computed } from "vue";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { useMeshCoreMessagePosition } from "../../meshchatnext/src/frontend/js/meshcoreMessagePosition";
import { meshcoreNotificationRoute } from "../../meshchatnext/src/frontend/js/meshcoreNotificationRoute";
const owner = "a1".repeat(32),
    target = "b2".repeat(32);
let wrapper;
const messages = (start, count) =>
    Array.from({ length: count }, (_, i) => ({ id: `m${start + i}`, created: start + i, direction: "in" }));
function setup(rows, view, focused = true) {
    vi.spyOn(document, "hasFocus").mockReturnValue(focused);
    vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible");
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function () {
        const index = this.dataset.messageId ? [...this.parentElement.children].indexOf(this) : -1;
        const top = index < 0 ? 0 : index * 40 - this.parentElement.scrollTop;
        return {
            top,
            bottom: top + (index < 0 ? 120 : 40),
            height: index < 0 ? 120 : 40,
            left: 0,
            right: 200,
            width: 200,
        };
    });
    const snapshot = ref({ owner, message_view: { target, kind: "channel", ...view } });
    const read = vi.fn().mockResolvedValue({});
    wrapper = mount({
        setup() {
            const list = ref(null),
                raw = computed(() => snapshot.value.testRows || rows);
            const state = useMeshCoreMessagePosition({
                snapshot,
                target: () => target,
                kind: "channel",
                list,
                rows: raw,
                markRead: read,
            });
            return { list, ...state };
        },
        template:
            '<div><div ref="list" @scroll="onScroll"><article v-for="row in visibleRows" :key="row.id" :data-message-id="row.id">{{row.id}}</article></div><button v-if="hasNewer" @click="loadNewer">Newer</button></div>',
    });
    Object.defineProperty(wrapper.vm.list, "clientHeight", { configurable: true, get: () => 120 });
    Object.defineProperty(wrapper.vm.list, "scrollHeight", {
        configurable: true,
        get: () => wrapper.findAll("article").length * 40,
    });
    return { read, snapshot };
}
beforeEach(() => {
    localStorage.clear();
    window.api = { get: vi.fn() };
});
afterEach(() => {
    wrapper?.unmount();
    vi.restoreAllMocks();
});
describe("MeshCore message entry", () => {
    it("opens at first unread and marks only the visible portion", async () => {
        const { read } = setup(messages(1, 20), { seen: 3, first_unread: { id: "m4", created: 4 } });
        await flushPromises();
        expect(wrapper.vm.list.scrollTop).toBe(120);
        expect(read).toHaveBeenCalledWith(6);
        expect(read).not.toHaveBeenCalledWith(20);
    });
    it("keeps the entry boundary fixed when a read acknowledgement refreshes", async () => {
        const { snapshot } = setup(messages(1, 20), { seen: 3, first_unread: { id: "m4", created: 4 } });
        await flushPromises();
        snapshot.value = {
            ...snapshot.value,
            message_view: { target, kind: "channel", seen: 6, first_unread: { id: "m7", created: 7 } },
        };
        await flushPromises();
        expect(wrapper.vm.firstUnreadId).toBe("m4");
        expect(wrapper.vm.list.scrollTop).toBe(120);
    });
    it("does not jump to the bottom when an entry near the end is acknowledged", async () => {
        const { snapshot } = setup(messages(1, 20), { seen: 18, first_unread: { id: "m19", created: 19 } });
        await flushPromises();
        const position = wrapper.vm.list.scrollTop;
        snapshot.value = { ...snapshot.value, message_view: { target, kind: "channel", seen: 20, first_unread: null } };
        await flushPromises();
        expect(wrapper.vm.list.scrollTop).toBe(position);
        expect(wrapper.vm.firstUnreadId).toBe("m19");
    });
    it("keeps the viewport still as background messages arrive and does not read them on focus", async () => {
        const { snapshot, read } = setup(messages(1, 3), { seen: 3, first_unread: null });
        await flushPromises();
        wrapper.vm.list.scrollTop = 0;
        vi.mocked(document.hasFocus).mockReturnValue(false);
        window.dispatchEvent(new Event("blur"));
        read.mockClear();
        snapshot.value = {
            ...snapshot.value,
            testRows: messages(1, 20),
            message_view: { target, kind: "channel", seen: 3, first_unread: { id: "m4", created: 4 } },
        };
        await flushPromises();
        expect(wrapper.vm.list.scrollTop).toBe(0);
        expect(read).not.toHaveBeenCalled();
        vi.mocked(document.hasFocus).mockReturnValue(true);
        window.dispatchEvent(new Event("focus"));
        expect(read).not.toHaveBeenCalled();
    });
    it("restores the previous position when there are no unread messages", async () => {
        localStorage.setItem(`meshcore-view:${owner}:channel:${target}`, JSON.stringify({ id: "m5", offset: -10 }));
        setup(messages(1, 20), { seen: 20, first_unread: null });
        await flushPromises();
        expect(wrapper.vm.list.scrollTop).toBe(170);
    });
    it("continues following live messages while already viewing the end", async () => {
        const { snapshot } = setup(messages(1, 3), { seen: 3, first_unread: null });
        await flushPromises();
        snapshot.value = { ...snapshot.value, testRows: messages(1, 4) };
        await flushPromises();
        expect(wrapper.vm.list.scrollTop).toBe(wrapper.vm.list.scrollHeight);
    });
    it("does not follow a background fetch that finishes after focus returns", async () => {
        const { snapshot } = setup(messages(1, 3), { seen: 3, first_unread: null });
        await flushPromises();
        wrapper.vm.list.scrollTop = 0;
        vi.mocked(document.hasFocus).mockReturnValue(false);
        window.dispatchEvent(new Event("blur"));
        vi.mocked(document.hasFocus).mockReturnValue(true);
        window.dispatchEvent(new Event("focus"));
        snapshot.value = {
            ...snapshot.value,
            testRows: messages(1, 20),
            message_view: { target, kind: "channel", seen: 3, first_unread: { id: "m4", created: 4 } },
        };
        await flushPromises();
        expect(wrapper.vm.list.scrollTop).toBe(0);
    });
    it("does not acknowledge background messages", async () => {
        const { read } = setup(messages(1, 20), { seen: 3, first_unread: { id: "m4", created: 4 } }, false);
        await flushPromises();
        expect(read).not.toHaveBeenCalled();
    });
    it("does not mark the latest messages read when the unread anchor fails to load", async () => {
        window.api.get.mockRejectedValueOnce(new Error("offline"));
        const { read } = setup(messages(1001, 20), { seen: 0, first_unread: { id: "m1", created: 1 } });
        await flushPromises();
        expect(wrapper.vm.positionError).toContain("first unread");
        expect(read).not.toHaveBeenCalled();
    });
    it("loads an unread boundary older than the latest history window", async () => {
        window.api.get.mockResolvedValueOnce({ data: { result: messages(1, 10) } });
        setup(messages(1001, 20), { seen: 0, first_unread: { id: "m1", created: 1 } });
        await flushPromises();
        expect(window.api.get).toHaveBeenCalledWith("/api/v1/meshcore/message-window", {
            params: { owner, kind: "channel", target, anchor: "m1" },
        });
        expect(wrapper.findAll("article")[0].text()).toBe("m1");
        expect(wrapper.find("button").exists()).toBe(true);
    });
});
describe("MeshCore notification destinations", () => {
    it.each([
        ["channel", "meshcore-channels"],
        ["room", "meshcore-nodes"],
        ["direct", "messages"],
    ])("routes a %s notification", async (kind, name) => {
        window.api.get.mockResolvedValue({ data: { result: { owner, target, kind } } });
        expect((await meshcoreNotificationRoute("meshcore-" + "c3".repeat(32))).name).toBe(name);
    });
    it("refuses unknown/other-identity destinations", async () => {
        window.api.get.mockResolvedValue({ data: { result: null } });
        await expect(meshcoreNotificationRoute("meshcore-" + "c3".repeat(32))).rejects.toThrow("unavailable");
    });
});
