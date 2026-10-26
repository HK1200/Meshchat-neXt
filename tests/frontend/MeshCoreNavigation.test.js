import { mount, flushPromises } from "@vue/test-utils";
import { describe, it, expect, vi, afterEach } from "vitest";
import { createRouter, createMemoryHistory } from "vue-router";
import MeshCoreNodesPage from "../../meshchatnext/src/frontend/components/meshcore/MeshCoreNodesPage.vue";
import { handleAppBack, installAndroidBackNavigation } from "../../meshchatnext/src/frontend/js/androidBackNavigation";
import MeshCoreSidebar from "../../meshchatnext/src/frontend/components/meshcore/MeshCoreSidebar.vue";
import MeshCoreChannelsPage from "../../meshchatnext/src/frontend/components/meshcore/MeshCoreChannelsPage.vue";
import MeshCoreBanishments from "../../meshchatnext/src/frontend/components/meshcore/MeshCoreBanishments.vue";
import AppSidebarNav from "../../meshchatnext/src/frontend/components/layout/AppSidebarNav.vue";
import AppSidebarClassicNav from "../../meshchatnext/src/frontend/components/layout/AppSidebarClassicNav.vue";
vi.mock("../../meshchatnext/src/frontend/js/DialogUtils", () => ({
    default: { confirm: vi.fn().mockResolvedValue(true) },
}));
const owner = "a1".repeat(32),
    channel = "b2".repeat(32),
    peer = "c3".repeat(32);
let wrapper;
afterEach(() => {
    wrapper?.unmount();
    wrapper = null;
    vi.restoreAllMocks();
});
function snapshot() {
    return {
        available: true,
        connected: true,
        owner,
        contacts: [],
        links: [],
        conversations: [],
        announces: [],
        profile_name: "Field radio",
        message_view: { target: channel, kind: "channel", seen: 0, first_unread: { id: "incoming", created: 1 } },
        channels: [{ slot: 1, channel_id: channel, name: "#field", kind: "public", unread: 2, muted: 0 }],
        nodes: [{ peer, name: "Hilltop", kind: 2 }],
        channel_messages: [
            {
                id: "incoming",
                direction: "in",
                sender: "Alice",
                text: "Alice: hello",
                created: Date.now() / 1000,
                state: "received",
            },
        ],
        channel_banishments: [{ channel_id: channel, channel_name: "#field", sender: "Bob", created: 1 }],
    };
}
async function router() {
    const value = createRouter({
        history: createMemoryHistory(),
        routes: [
            { path: "/", name: "home", component: { template: "<div/>" } },
            { path: "/meshcore/channels/:channelId?", name: "meshcore-channels", component: { template: "<div/>" } },
            { path: "/meshcore/nodes/:peer?", name: "meshcore-nodes", component: { template: "<div/>" } },
        ],
    });
    await value.push("/");
    await value.isReady();
    return value;
}
describe("MeshCore navigation and channel boundaries", () => {
    it("keeps message details open across equivalent snapshot refreshes and closes on identity change", async () => {
        const data = snapshot();
        window.api = {
            get: vi.fn(async () => ({ data: { result: structuredClone(data) } })),
            post: vi.fn(async () => ({ data: { result: {} } })),
        };
        wrapper = mount(MeshCoreChannelsPage, {
            props: { channelId: channel },
            global: { stubs: { MeshCoreMessageDetails: true } },
        });
        await flushPromises();
        await wrapper.get('[aria-label="Show message path details"]').trigger("click");
        const details = () => wrapper.findComponent({ name: "MeshCoreMessageDetails" });
        expect(details().props("row").id).toBe("incoming");
        await wrapper.get('select[aria-label="Channel notifications"]').setValue("mentions");
        await flushPromises();
        expect(details().props("row").id).toBe("incoming");
        data.owner = "d4".repeat(32);
        await wrapper.get('select[aria-label="Channel notifications"]').setValue("all");
        await flushPromises();
        expect(details().props("row")).toBeNull();
    });

    it("expands channel unread badges and routes collapsed nodes to their own page", async () => {
        const data = snapshot();
        window.api = { get: vi.fn().mockResolvedValue({ data: { result: data } }) };
        const navigation = await router();
        wrapper = mount(MeshCoreSidebar, { global: { plugins: [navigation], stubs: { RouterLink: false } } });
        await flushPromises();
        await wrapper.find('button[aria-label="MeshCore Channels"]').trigger("click");
        expect(wrapper.text()).toContain("#field");
        expect(wrapper.text()).toContain("2");
        expect(wrapper.findAll("a").some((link) => link.attributes("href").endsWith(channel))).toBe(true);
        await wrapper.setProps({ collapsed: true });
        await wrapper.find('button[aria-label="MeshCore Nodes"]').trigger("click");
        await flushPromises();
        expect(navigation.currentRoute.value.name).toBe("meshcore-nodes");
    });
    it("can hide Public and delete another channel with slot and identity guards", async () => {
        const data = snapshot();
        data.channels.unshift({ slot: 0, channel_id: "d4".repeat(32), name: "Public", kind: "public", unread: 0 });
        window.api = {
            get: vi.fn(async () => ({ data: { result: structuredClone(data) } })),
            post: vi.fn(async (path, body) => {
                if (path.endsWith("channel-visibility"))
                    data.channels.find((r) => r.channel_id === body.channel).hidden = body.hidden;
                if (path.endsWith("channel-remove"))
                    data.channels = data.channels.filter((r) => r.channel_id !== body.expected_channel_id);
                return { data: { result: {} } };
            }),
        };
        wrapper = mount(MeshCoreChannelsPage, { global: { plugins: [await router()] } });
        await flushPromises();
        expect(wrapper.find('[aria-label="Delete Public"]').exists()).toBe(false);
        await wrapper.get('[aria-label="Hide Public"]').trigger("click");
        await flushPromises();
        expect(wrapper.find('[aria-label="Show Public"]').exists()).toBe(true);
        await wrapper.get('[aria-label="Delete #field"]').trigger("click");
        await flushPromises();
        expect(window.api.post).toHaveBeenLastCalledWith("/api/v1/meshcore/channel-remove", {
            slot: 1,
            expected_channel_id: channel,
            expected_owner: owner,
        });
        expect(wrapper.find('[aria-label="Delete #field"]').exists()).toBe(false);
    });
    it("reorders channels with arrows only, preserving the list on save failure", async () => {
        const data = snapshot();
        data.channels.push({ slot: 4, channel_id: peer, name: "#second", kind: "private" });
        window.api = {
            get: vi.fn().mockImplementation(async () => ({ data: { result: structuredClone(data) } })),
            post: vi.fn().mockImplementation(async (path, body) => {
                data.channels.sort((a, b) => body.channels.indexOf(a.channel_id) - body.channels.indexOf(b.channel_id));
                return { data: { result: {} } };
            }),
        };
        wrapper = mount(MeshCoreChannelsPage, { global: { plugins: [await router()] } });
        await flushPromises();
        expect(wrapper.get('button[aria-label="Move #field up"]').element.disabled).toBe(true);
        await wrapper.get('button[aria-label="Move #second up"]').trigger("click");
        await flushPromises();
        expect(window.api.post).toHaveBeenLastCalledWith("/api/v1/meshcore/channel-order", {
            channels: [peer, channel],
            expected_owner: owner,
        });
        expect(wrapper.find('[draggable="true"]').exists()).toBe(false);
        await wrapper.get('button[aria-label="Move #field up"]').trigger("click");
        await flushPromises();
        expect(window.api.post).toHaveBeenLastCalledWith("/api/v1/meshcore/channel-order", {
            channels: [channel, peer],
            expected_owner: owner,
        });
        window.api.post.mockRejectedValueOnce(new Error("offline"));
        await wrapper.get('button[aria-label="Move #second up"]').trigger("click");
        await flushPromises();
        expect(wrapper.text()).toContain("Could not save channel order");
        expect(wrapper.get('button[aria-label="Move #field up"]').element.disabled).toBe(true);
    });
    it("reads without a refresh loop, sends only to the guarded channel, and banishes a displayed name", async () => {
        const data = snapshot();
        vi.spyOn(document, "hasFocus").mockReturnValue(true);
        vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
            top: 0,
            bottom: 200,
            height: 200,
            left: 0,
            right: 100,
            width: 100,
        });
        window.api = {
            get: vi.fn().mockImplementation(async () => ({ data: { result: structuredClone(data) } })),
            post: vi.fn().mockImplementation(async (path) => {
                if (path.endsWith("/channel-banish")) data.channel_messages = [];
                return { data: { result: { state: "submitted" } } };
            }),
        };
        wrapper = mount(MeshCoreChannelsPage, { props: { channelId: channel } });
        await flushPromises();
        await flushPromises();
        expect(window.api.get).toHaveBeenCalledTimes(1);
        expect(window.api.post).toHaveBeenCalledWith(
            "/api/v1/meshcore/channel-read",
            expect.objectContaining({ channel, expected_owner: owner })
        );
        await wrapper.find("textarea").setValue("hello channel");
        // A preference refresh replaces the snapshot without changing identity.
        await wrapper.find('select[aria-label="Channel notifications"]').setValue("mentions");
        await flushPromises();
        expect(window.api.post).toHaveBeenCalledWith("/api/v1/meshcore/channel-mute", {
            channel,
            muted: false,
            mentions_only: true,
            expected_owner: owner,
        });
        expect(wrapper.find("textarea").element.value).toBe("hello channel");
        await wrapper.get('[aria-label="Message actions for Alice"]').trigger("click");
        await wrapper
            .findAll(".context-item")
            .find((item) => item.text().includes("Reply"))
            .trigger("click");
        await flushPromises();
        expect(wrapper.find("textarea").element.value).toBe("@[Alice] hello channel");
        expect(window.api.post.mock.calls.some(([path]) => path.endsWith("/channel-message"))).toBe(false);
        await wrapper.find("form").trigger("submit");
        await flushPromises();
        expect(window.api.post).toHaveBeenCalledWith(
            "/api/v1/meshcore/channel-message",
            expect.objectContaining({
                slot: 1,
                text: "@[Alice] hello channel",
                expected_channel_id: channel,
                expected_owner: owner,
                request_id: expect.any(String),
            })
        );
        await wrapper.get('[aria-label="Message actions for Alice"]').trigger("click");
        await wrapper
            .findAll(".context-item")
            .find((item) => item.text().includes("Banish"))
            .trigger("click");
        await flushPromises();
        expect(window.api.post).toHaveBeenCalledWith("/api/v1/meshcore/channel-banish", {
            channel,
            message: "incoming",
            expected_owner: owner,
        });
        expect(wrapper.findAll("article")).toHaveLength(0);
        expect(window.api.post.mock.calls.every(([path]) => !path.includes("lxmf"))).toBe(true);
    });
    it("lifts a MeshCore channel name filter from Banishment without touching Reticulum blocks", async () => {
        const data = snapshot();
        window.api = {
            get: vi.fn().mockResolvedValue({ data: { result: data } }),
            post: vi.fn().mockResolvedValue({ data: { result: {} } }),
        };
        wrapper = mount(MeshCoreBanishments);
        await flushPromises();
        expect(wrapper.text()).toContain("local name filter");
        await wrapper.find("button").trigger("click");
        await flushPromises();
        expect(window.api.post).toHaveBeenCalledWith("/api/v1/meshcore/channel-unbanish", {
            channel,
            sender: "Bob",
            expected_owner: owner,
        });
    });
    it("keeps the grouped navigation insertion unique when Relay Chat is in More", () => {
        wrapper = mount(AppSidebarNav, {
            props: {
                primaryNavGroups: [
                    { id: "communicate", items: [{ id: "contacts", route: { name: "contacts" }, label: "Contacts" }] },
                ],
                moreNavItems: [{ id: "relay-chat", route: { name: "relay-chat" }, label: "Relay Chat" }],
                isShowingMoreNav: true,
            },
            slots: { "meshcore-navigation": '<div data-testid="meshcore-slot">MeshCore</div>' },
            global: {
                mocks: { $t: (key) => key },
                stubs: { RouterLink: { template: '<a><slot :isActive="false" :navigate="()=>{}"/></a>' } },
            },
        });
        expect(wrapper.findAll('[data-testid="meshcore-slot"]')).toHaveLength(1);
        expect(
            wrapper.find('[data-testid="meshcore-slot"]').element.parentElement.previousElementSibling.dataset.navItemId
        ).toBe("relay-chat");
    });
    it("inserts MeshCore navigation immediately below Relay Chat in the existing classic sidebar", () => {
        wrapper = mount(AppSidebarClassicNav, {
            props: {
                navItems: [
                    { id: "contacts", route: { name: "contacts" }, label: "Contacts" },
                    { id: "relay-chat", route: { name: "relay-chat" }, label: "Relay Chat" },
                    { id: "map", route: { name: "map" }, label: "Map" },
                ],
            },
            slots: { "meshcore-navigation": '<div data-testid="meshcore-slot">MeshCore</div>' },
            global: {
                mocks: { $t: (key) => key },
                stubs: { RouterLink: { template: '<a><slot :isActive="false" :navigate="()=>{}"/></a>' } },
            },
        });
        const inserted = wrapper.find('[data-testid="meshcore-slot"]').element.parentElement;
        expect(inserted.previousElementSibling.dataset.navItemId).toBe("relay-chat");
        expect(inserted.nextElementSibling.dataset.navItemId).toBe("map");
    });
});

it("Android Back hides node discovery and keeps the saved-nodes page", async () => {
    const data = snapshot();
    window.api = {
        get: vi.fn(async () => ({ data: { result: structuredClone(data) } })),
        post: vi.fn(async () => ({ data: { result: { nodes: [] } } })),
    };
    const navigation = await router();
    const dispose = installAndroidBackNavigation(navigation, {});
    await navigation.push({ name: "meshcore-nodes" });
    wrapper = mount(MeshCoreNodesPage, { attachTo: document.body, global: { plugins: [navigation] } });
    await flushPromises();
    const discover = wrapper.findAll("button").find((b) => b.text() === "Discover new nodes");
    await discover.trigger("click");
    await flushPromises();
    expect(wrapper.find("[data-app-back-scope]").exists()).toBe(true);
    vi.spyOn(HTMLElement.prototype, "getClientRects").mockImplementation(() => [{}]);
    handleAppBack(navigation);
    await flushPromises();
    expect(wrapper.find("[data-app-back-scope]").exists()).toBe(false);
    expect(navigation.currentRoute.value.name).toBe("meshcore-nodes");
    expect(wrapper.text()).toContain("Saved repeaters, room servers and sensors");
    dispose();
});

it("shows a scan reply immediately even before the announces snapshot catches up", async () => {
    const data = snapshot();
    data.announces = [{ peer: "e5".repeat(32), name: "Older repeater", kind: 2 }];
    const found = "d4".repeat(32);
    window.api = {
        get: vi.fn(async () => ({ data: { result: structuredClone(data) } })),
        post: vi.fn(async () => ({ data: { result: { nodes: [{ peer: found, kind: 3 }] } } })),
    };
    const navigation = await router();
    await navigation.push({ name: "meshcore-nodes" });
    wrapper = mount(MeshCoreNodesPage, { global: { plugins: [navigation] } });
    await flushPromises();
    await wrapper
        .findAll("button")
        .find((b) => b.text() === "Discover new nodes")
        .trigger("click");
    await flushPromises();
    const current = wrapper.get('[aria-label="Replied to this scan"]');
    expect(current.text()).toContain(found);
    expect(current.text()).toContain("Room server");
    expect(current.text()).not.toContain("Older repeater");
    expect(wrapper.get('[aria-label="Previously heard"]').text()).toContain("Older repeater");
    expect(wrapper.text()).toContain("1 nearby node replied");
});
