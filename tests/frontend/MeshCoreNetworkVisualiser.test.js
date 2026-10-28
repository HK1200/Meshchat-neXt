import { it, expect, vi, beforeEach, afterEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import { installAndroidBackNavigation } from "../../meshchatnext/src/frontend/js/androidBackNavigation";
import Component from "../../meshchatnext/src/frontend/components/network-visualiser/MeshCoreNetworkVisualiser.vue";
const mock = vi.hoisted(() => ({ setData: vi.fn(), destroy: vi.fn(), on: vi.fn(), fit: vi.fn() }));
vi.mock("vis-network", () => ({
    Network: class {
        constructor() {
            Object.assign(this, mock);
        }
    },
}));
vi.mock("vis-data", () => ({
    DataSet: class {
        constructor(rows) {
            this.rows = rows;
        }
    },
}));
const a = "a1".repeat(32),
    b = "b2".repeat(32),
    peer = "c3".repeat(32);
let wrappers = [];
beforeEach(() => {
    vi.clearAllMocks();
});
afterEach(() => {
    wrappers.forEach((w) => w.unmount());
    wrappers = [];
});
async function open(get) {
    window.api = { get };
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: "/", component: Component }] });
    await router.push("/");
    await router.isReady();
    const w = mount(Component, { attachTo: document.body, global: { plugins: [router] } });
    wrappers.push(w);
    await flushPromises();
    return w;
}
const radios = [
    { id: "one", label: "First radio", owner: a, connected: true },
    { id: "two", label: "Second radio", owner: b, connected: false },
];
it("reads only selected MeshCore topology, renders text safely and destroys resources", async () => {
    const get = vi.fn(async (url) => ({
        data: url.endsWith("/status")
            ? { radios, radio_id: "one" }
            : { result: { owner: a, connected: true, nodes: [{ peer, name: "<img onerror=alert(1)>", kind: 2 }] } },
    }));
    const w = await open(get);
    expect(get.mock.calls.map(([url]) => url).every((url) => url.includes("/meshcore/"))).toBe(true);
    expect(get.mock.calls[1][1].params).toEqual({ radio: "one", owner: a });
    const click = mock.on.mock.calls.find(([name]) => name === "click")[1];
    click({ nodes: [peer] });
    await w.vm.$nextTick();
    expect(w.text()).toContain("<img onerror=alert(1)>");
    expect(w.find("img").exists()).toBe(false);
    w.unmount();
    wrappers = [];
    expect(mock.destroy).toHaveBeenCalledOnce();
});
it("rejects late responses from a previously selected radio", async () => {
    let resolveFirst;
    const get = vi.fn((url) =>
        url.endsWith("/status")
            ? Promise.resolve({ data: { radios, radio_id: "one" } })
            : get.mock.calls.filter(([url]) => url.endsWith("/topology")).length === 1
              ? new Promise((resolve) => {
                    resolveFirst = resolve;
                })
              : Promise.resolve({ data: { result: { owner: b, connected: false, nodes: [] } } })
    );
    const w = await open(get);
    await w.get("select").setValue("two");
    await flushPromises();
    expect(w.text()).toContain("Companion offline");
    resolveFirst({ data: { result: { owner: a, connected: true, nodes: [{ peer, name: "Wrong radio" }] } } });
    await flushPromises();
    expect(mock.setData.mock.calls.at(-1)[0].nodes.rows.some((node) => node.label === "Wrong radio")).toBe(false);
    expect(get.mock.calls.at(-1)[1].params).toEqual({ radio: "two", owner: b });
});
it("clears the diagram when the selected identity changes unexpectedly", async () => {
    const w = await open(
        vi.fn(async (url) => ({
            data: url.endsWith("/status")
                ? { radios, radio_id: "one" }
                : { result: { owner: b, nodes: [{ peer, name: "Wrong owner" }] } },
        }))
    );
    expect(w.get("[role=alert]").text()).toContain("identity changed");
    expect(mock.setData.mock.calls.at(-1)[0].nodes.rows).toHaveLength(1);
});

it("Close and Android Back dismiss details with the real global Back interception installed", async () => {
    const w = await open(
        vi.fn(async (url) => ({
            data: url.endsWith("/status")
                ? { radios, radio_id: "one" }
                : { result: { owner: a, connected: true, nodes: [{ peer, name: "Repeater", kind: 2 }] } },
        }))
    );
    const rects = vi.spyOn(HTMLElement.prototype, "getClientRects").mockReturnValue([{}]);
    const uninstall = installAndroidBackNavigation(w.vm.$router);
    const click = mock.on.mock.calls.find(([name]) => name === "click")[1];
    try {
        click({ nodes: [peer] });
        await w.vm.$nextTick();
        w.get('[aria-label="Close node information"]').element.click();
        await w.vm.$nextTick();
        expect(w.find('[aria-label="MeshCore node information"]').exists()).toBe(false);
        click({ nodes: [peer] });
        await w.vm.$nextTick();
        expect(window.meshchatHandleBack()).toBe(true);
        await w.vm.$nextTick();
        expect(w.find('[aria-label="MeshCore node information"]').exists()).toBe(false);
        expect(w.vm.$route.fullPath).toBe("/");
    } finally {
        uninstall();
        rects.mockRestore();
    }
});
