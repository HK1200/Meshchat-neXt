import { mount, flushPromises } from "@vue/test-utils";
import { describe, it, expect, vi, afterEach } from "vitest";
import MeshCoreNodeSession from "../../meshchatnext/src/frontend/components/meshcore/MeshCoreNodeSession.vue";
const owner = "a1".repeat(32),
    peer = "b2".repeat(32);
let wrapper;
afterEach(() => {
    wrapper?.unmount();
    localStorage.clear();
    vi.restoreAllMocks();
});
function setup(kind = 3) {
    window.api = { post: vi.fn().mockResolvedValue({ data: { result: { state: "verified", is_admin: false } } }) };
    wrapper = mount(MeshCoreNodeSession, {
        attachTo: document.body,
        props: {
            node: { peer, kind, name: "Test node" },
            snapshot: { owner, connected: true, messages: [], node_sessions: {} },
        },
    });
}
function button(label) {
    return wrapper.findAll("button").find((x) => x.text() === label);
}
describe("MeshCore node sessions", () => {
    it("does not log in automatically, guards owner and clears the password", async () => {
        setup();
        expect(window.api.post).not.toHaveBeenCalled();
        await wrapper.find('input[type="password"]').setValue("temporary-password");
        await wrapper.find("form").trigger("submit");
        await flushPromises();
        expect(window.api.post).toHaveBeenCalledWith(
            "/api/v1/meshcore/node-login",
            { peer, expected_owner: owner, password: "temporary-password" },
            { timeout: 150000 }
        );
        expect(wrapper.find("input").element.value).toBe("");
        expect(wrapper.text()).toContain("Login verified.");
        expect(wrapper.emitted("changed")).toHaveLength(1);
    });
    it("requires current login for posts, uses a stable request id, and disables repeat after uncertainty", async () => {
        setup();
        expect(button("Send to room").attributes("disabled")).toBeDefined();
        await wrapper.setProps({
            snapshot: { owner, connected: true, node_sessions: { [peer]: { state: "verified" } }, messages: [] },
        });
        await wrapper.find("textarea").setValue("room post");
        window.api.post.mockRejectedValueOnce(new Error("timeout"));
        await wrapper.findAll("form")[1].trigger("submit");
        await flushPromises();
        expect(window.api.post).toHaveBeenCalledWith(
            "/api/v1/meshcore/room-message",
            { peer, expected_owner: owner, text: "room post", request_id: expect.any(String) },
            { timeout: 150000 }
        );
        expect(button("Send to room").attributes("disabled")).toBeDefined();
        await wrapper.findAll("form")[1].trigger("submit");
        await flushPromises();
        expect(window.api.post).toHaveBeenCalledTimes(1);
    });
    it("replies publicly to the selected room author and retains text after a safe preflight failure", async () => {
        setup();
        await wrapper.setProps({
            snapshot: {
                owner,
                connected: true,
                node_sessions: { [peer]: { state: "verified" } },
                contacts: [{ peer: "1234abcd" + "00".repeat(28), name: "Alice", active: true }],
                messages: [
                    {
                        id: "reply-post",
                        peer,
                        direction: "in",
                        text: "Hello",
                        created: 1,
                        payload: JSON.stringify({ event: { txt_type: 2, signature: "1234abcd" } }),
                    },
                ],
            },
        });
        await button("Reply").trigger("click");
        await wrapper.find("textarea").setValue("Hi Alice");
        window.api.post.mockResolvedValueOnce({
            data: { result: { state: "not_sent", reason: "Clock is ahead; wait" } },
        });
        await wrapper.findAll("form")[1].trigger("submit");
        await flushPromises();
        expect(window.api.post).toHaveBeenCalledWith(
            "/api/v1/meshcore/room-message",
            {
                peer,
                expected_owner: owner,
                text: "> Alice [1234abcd]: Hello\nHi Alice",
                request_id: expect.any(String),
            },
            { timeout: 150000 }
        );
        expect(wrapper.text()).toContain("Post was not sent.");
        expect(wrapper.find("textarea").element.value).toBe("Hi Alice");
        expect(button("Send to room").attributes("disabled")).toBeUndefined();
        await button("Cancel reply").trigger("click");
        expect(wrapper.find("textarea").element.value).toBe("Hi Alice");
        await button("Reply").trigger("click");
        await wrapper.setProps({ snapshot: { owner: "dd".repeat(32), connected: true, messages: [] } });
        expect(wrapper.text()).not.toContain("Replying to Alice");
        expect(wrapper.find("textarea").element.value).toBe("");
    });
    it("unlocks after the exact pending post is acknowledged without resending", async () => {
        setup();
        const snapshot = { owner, connected: true, node_sessions: { [peer]: { state: "verified" } }, messages: [] };
        await wrapper.setProps({ snapshot });
        await wrapper.find("textarea").setValue("uncertain post");
        window.api.post.mockRejectedValueOnce(new Error("lost HTTP response"));
        await wrapper.findAll("form")[1].trigger("submit");
        await flushPromises();
        const requestId = window.api.post.mock.calls[0][1].request_id;
        expect(button("Send to room").attributes("disabled")).toBeDefined();
        await wrapper.setProps({
            snapshot: {
                ...snapshot,
                messages: [{ id: "other", peer, direction: "out", state: "delivered", text: "other", created: 1 }],
            },
        });
        expect(wrapper.find("textarea").attributes("disabled")).toBeDefined();
        await wrapper.setProps({
            snapshot: {
                ...snapshot,
                messages: [
                    { id: requestId, peer, direction: "out", state: "delivered", text: "uncertain post", created: 2 },
                ],
            },
        });
        expect(wrapper.find("textarea").attributes("disabled")).toBeUndefined();
        expect(wrapper.find("textarea").element.value).toBe("");
        expect(wrapper.text()).toContain("It was not sent again.");
        expect(window.api.post).toHaveBeenCalledTimes(1);
    });
    it("shows room posts separately from CLI text and clears secrets on owner changes", async () => {
        setup();
        await wrapper.find("input").setValue("secret");
        await wrapper.setProps({
            snapshot: {
                owner: "c3".repeat(32),
                connected: true,
                node_sessions: {},
                messages: [
                    {
                        id: "post",
                        peer,
                        text: "room hello",
                        direction: "in",
                        created: 1,
                        payload: JSON.stringify({ event: { txt_type: 2, signature: "1234abcd" } }),
                    },
                    {
                        id: "cli",
                        peer,
                        text: "CLI output",
                        direction: "in",
                        created: 2,
                        payload: JSON.stringify({ event: { txt_type: 1 } }),
                    },
                ],
            },
        });
        expect(wrapper.find("input").element.value).toBe("");
        expect(wrapper.text()).toContain("Author 1234abcd");
        expect(wrapper.text()).toContain("room hello");
        expect(wrapper.text()).not.toContain("CLI output");
    });
    it("offers repeater login and status without a room composer", async () => {
        setup(2);
        expect(wrapper.find("textarea").exists()).toBe(false);
        expect(button("Request status").attributes("disabled")).toBeDefined();
        await wrapper.setProps({
            snapshot: { owner, connected: true, node_sessions: { [peer]: { state: "verified" } } },
        });
        window.api.post.mockResolvedValueOnce({
            data: { result: { state: "received", values: { battery_mv: 4100 } } },
        });
        await button("Request status").trigger("click");
        await flushPromises();
        expect(wrapper.text()).toContain("4100");
        expect(window.api.post).toHaveBeenCalledTimes(1);
    });
    it("shows administrator controls only for a current administrator login", async () => {
        setup();
        const snapshot = {
            owner,
            connected: true,
            messages: [],
            node_sessions: { [peer]: { state: "verified", is_admin: false } },
        };
        await wrapper.setProps({ snapshot });
        expect(wrapper.find('[aria-label="MeshCore administrator controls"]').exists()).toBe(false);
        await wrapper.setProps({
            snapshot: { ...snapshot, node_sessions: { [peer]: { state: "verified", is_admin: true } } },
        });
        expect(wrapper.text()).toContain("Administrator login verified");
        await button("Restart server").trigger("click");
        expect(button("Confirm restart").attributes("disabled")).toBeDefined();
        await wrapper.find('[aria-label="MeshCore administrator controls"] input[type="checkbox"]').setValue(true);
        window.api.post.mockResolvedValueOnce({ data: { result: { state: "submitted", text: "Restart submitted" } } });
        await button("Confirm restart").trigger("submit");
        await flushPromises();
        expect(window.api.post).toHaveBeenCalledWith(
            "/api/v1/meshcore/node-admin",
            { peer, expected_owner: owner, action: "reboot", value: "", confirmed: true },
            { timeout: 150000 }
        );
        await wrapper.setProps({ snapshot: { ...snapshot, connected: false } });
        expect(wrapper.find('[aria-label="MeshCore administrator controls"]').exists()).toBe(false);
    });
    it("describes zero-hop routes as direct without implying logout", async () => {
        setup();
        window.api.post.mockResolvedValueOnce({
            data: { result: { state: "route_received", out_hops: 0, in_hops: 0 } },
        });
        await button("Check route").trigger("click");
        await flushPromises();
        expect(wrapper.text()).toContain("Direct connection · no repeaters");
        expect(wrapper.text()).toContain("login status unchanged");
        expect(wrapper.text()).not.toContain("No login was attempted");
    });

    it("hides login inputs while verified and restores them after logout or disconnect", async () => {
        setup();
        expect(wrapper.find('[aria-label="MeshCore server password"]').exists()).toBe(true);
        const snapshot = {
            owner,
            connected: true,
            messages: [],
            node_sessions: { [peer]: { state: "verified", is_admin: true } },
        };
        await wrapper.setProps({ snapshot });
        expect(wrapper.find('[aria-label="MeshCore server password"]').exists()).toBe(false);
        expect(button("Log in")).toBeUndefined();
        expect(button("Show password")).toBeUndefined();
        expect(button("Log out")).toBeDefined();
        window.api.post.mockResolvedValueOnce({ data: { result: { state: "submitted" } } });
        await button("Log out").trigger("click");
        await flushPromises();
        expect(window.api.post).toHaveBeenCalledWith(
            "/api/v1/meshcore/node-logout",
            { peer, expected_owner: owner },
            { timeout: 150000 }
        );
        await wrapper.setProps({ snapshot: { ...snapshot, node_sessions: {} } });
        expect(wrapper.find('[aria-label="MeshCore server password"]').exists()).toBe(true);
        expect(button("Log in")).toBeDefined();
        expect(button("Log out")).toBeUndefined();
        await wrapper.setProps({ snapshot });
        await wrapper.setProps({ snapshot: { ...snapshot, connected: false } });
        expect(wrapper.find('[aria-label="MeshCore server password"]').attributes("disabled")).toBeDefined();
    });

    it("runs firmware and repeat reads on tap and confirms repeat changes inline", async () => {
        setup(2);
        await wrapper.setProps({
            snapshot: {
                owner,
                connected: true,
                messages: [],
                node_sessions: { [peer]: { state: "verified", is_admin: true } },
            },
        });
        window.api.post.mockResolvedValueOnce({
            data: { result: { state: "admin_response", text: "Version fixture" } },
        });
        await button("View firmware version").trigger("click");
        await flushPromises();
        expect(button("View firmware version").element.closest("details").textContent).toContain("Version fixture");
        expect(window.api.post).toHaveBeenCalledExactlyOnceWith(
            "/api/v1/meshcore/node-admin",
            { peer, expected_owner: owner, action: "version", value: "", confirmed: false },
            { timeout: 150000 }
        );
        window.api.post.mockResolvedValueOnce({ data: { result: { state: "admin_response", text: "> on" } } });
        await button("View repeat setting").trigger("click");
        await flushPromises();
        expect(button("View repeat setting").element.closest("details").textContent).toContain("> on");
        await button("Change repeat setting").trigger("click");
        expect(window.api.post).toHaveBeenCalledTimes(2);
        expect(button("Save repeat setting").attributes("disabled")).toBeDefined();
        await wrapper.get('[aria-label="Repeater forwarding"]').setValue("off");
        window.api.post.mockResolvedValueOnce({ data: { result: { state: "admin_response", text: "OK" } } });
        await button("Save repeat setting").trigger("submit");
        await flushPromises();
        expect(window.api.post).toHaveBeenLastCalledWith(
            "/api/v1/meshcore/node-admin",
            { peer, expected_owner: owner, action: "set-repeat", value: "off", confirmed: false },
            { timeout: 150000 }
        );
    });

    it("allows another admin command without reconnecting after a timeout", async () => {
        setup();
        const snapshot = {
            owner,
            connected: true,
            messages: [],
            node_sessions: { [peer]: { state: "verified", is_admin: true } },
        };
        await wrapper.setProps({ snapshot });
        window.api.post.mockResolvedValueOnce({ data: { result: { state: "uncertain" } } });
        await button("View firmware version").trigger("click");
        await flushPromises();
        expect(wrapper.findAll('[role="alert"]')).toHaveLength(1);
        expect(button("Reconnect MeshCore")).toBeUndefined();
        await wrapper.setProps({
            snapshot: { ...snapshot, node_operations: { [peer]: { operation: "admin", stage: "server_timeout" } } },
        });
        window.api.post.mockResolvedValueOnce({
            data: { result: { state: "admin_unverified_response", text: "> on" } },
        });
        await button("View firmware version").trigger("click");
        await flushPromises();
        expect(window.api.post).toHaveBeenCalledTimes(2);
        expect(wrapper.text()).toContain("Unverified reply (may be from an earlier command): > on");
        expect(wrapper.findAll('[role="alert"]')).toHaveLength(0);
    });

    it("requires matching masked room passwords and clears both before sending", async () => {
        setup();
        await wrapper.setProps({
            snapshot: {
                owner,
                connected: true,
                messages: [],
                node_sessions: { [peer]: { state: "verified", is_admin: true } },
            },
        });
        await button("Change room password (non-administrator)").trigger("click");
        const value = wrapper.find('[aria-label="Administrator setting value"]');
        const confirm = wrapper.find('[aria-label="Confirm room password"]');
        expect(value.attributes("type")).toBe("password");
        await value.setValue("temporary");
        await confirm.setValue("different");
        await wrapper.find('[aria-label="MeshCore administrator controls"] input[type="checkbox"]').setValue(true);
        expect(button("Save room password").attributes("disabled")).toBeDefined();
        await confirm.setValue("temporary");
        expect(button("Save room password").attributes("disabled")).toBeUndefined();
        let finish;
        window.api.post.mockImplementationOnce(
            () =>
                new Promise((resolve) => {
                    finish = resolve;
                })
        );
        await button("Save room password").trigger("submit");
        expect(value.element.value).toBe("");
        expect(confirm.element.value).toBe("");
        expect(window.api.post).toHaveBeenCalledWith(
            "/api/v1/meshcore/node-admin",
            { peer, expected_owner: owner, action: "set-room-password", value: "temporary", confirmed: true },
            { timeout: 150000 }
        );
        finish({ data: { result: { state: "admin_response", text: "Room password changed." } } });
        await flushPromises();
        expect(wrapper.text()).not.toContain("temporary");
        await value.setValue("x".repeat(16));
        await confirm.setValue("x".repeat(16));
        expect(button("Save room password").attributes("disabled")).toBeDefined();
        await wrapper.setProps({ node: { peer, kind: 2, name: "Repeater" } });
        expect(button("Change room password (non-administrator)")).toBeUndefined();
    });

    it("clears stale timeout blocks when reconnect occurs between UI polls", async () => {
        setup();
        const snapshot = {
            owner,
            connection_id: "first",
            connected: true,
            messages: [],
            node_sessions: { [peer]: { state: "verified", is_admin: true } },
        };
        await wrapper.setProps({ snapshot });
        window.api.post.mockResolvedValueOnce({ data: { result: { state: "uncertain" } } });
        await button("View firmware version").trigger("click");
        await flushPromises();
        expect(wrapper.findAll('[role="alert"]')).toHaveLength(1);
        await wrapper.setProps({ snapshot: { ...snapshot, connection_id: "second" } });
        expect(wrapper.findAll('[role="alert"]')).toHaveLength(0);
        expect(button("View firmware version").attributes("disabled")).toBeUndefined();
    });

    it("does not turn an app-rejected admin request into a radio timeout", async () => {
        setup();
        await wrapper.setProps({
            snapshot: {
                owner,
                connected: true,
                messages: [],
                node_sessions: { [peer]: { state: "verified", is_admin: true } },
            },
        });
        window.api.post.mockRejectedValueOnce({ response: { status: 400 } });
        await button("View firmware version").trigger("click");
        await flushPromises();
        expect(wrapper.text()).toContain("The app rejected this request");
        expect(button("Reconnect MeshCore")).toBeUndefined();
        expect(button("View firmware version").attributes("disabled")).toBeUndefined();
    });
    it("discards an administrator response after switching the selected radio", async () => {
        setup(2);
        const snapshot = {
            owner,
            radio_id: "first",
            connected: true,
            messages: [],
            node_sessions: { [peer]: { state: "verified", is_admin: true } },
        };
        await wrapper.setProps({ snapshot });
        let finish;
        window.api.post.mockImplementationOnce(
            () =>
                new Promise((resolve) => {
                    finish = resolve;
                })
        );
        await button("View firmware version").trigger("click");
        await wrapper.setProps({ snapshot: { ...snapshot, radio_id: "second" } });
        finish({ data: { result: { state: "admin_response", text: "Old radio private response" } } });
        await flushPromises();
        expect(wrapper.text()).not.toContain("Old radio private response");
        expect(window.api.post).toHaveBeenCalledTimes(1);
    });
});

describe("Task-based node navigation and room author names", () => {
    it("opens rooms on Messages and repeaters on Overview without sending commands", async () => {
        setup();
        const panel = (name) => wrapper.find(`[aria-label="${name}"]`);
        expect(panel("Room conversation").isVisible()).toBe(true);
        expect(panel("Node access").isVisible()).toBe(false);
        expect(panel("Manage node").isVisible()).toBe(false);
        await button("Access").trigger("click");
        expect(panel("Node access").isVisible()).toBe(true);
        expect(panel("Room conversation").isVisible()).toBe(false);
        expect(window.api.post).not.toHaveBeenCalled();
        await wrapper.setProps({ node: { peer: "cc".repeat(32), kind: 2, name: "Repeater" } });
        expect(button("Overview").attributes("aria-pressed")).toBe("true");
        expect(panel("Node status").isVisible()).toBe(true);
        expect(panel("Room conversation").exists()).toBe(false);
    });
    it("logs in to the selected repeater once and honors logout until the next visit", async () => {
        setup(2);
        const snapshot = { ...wrapper.props("snapshot"), radio_id: "travel", connection_id: "current" };
        await wrapper.setProps({ snapshot, visit: "first" });
        await flushPromises();
        expect(window.api.post).toHaveBeenCalledExactlyOnceWith(
            "/api/v1/meshcore/repeater-auto-login",
            { peer, expected_owner: owner, expected_connection_id: "current" },
            { timeout: 150000, params: { radio: "travel" } }
        );
        await wrapper.setProps({ snapshot: { ...snapshot, node_sessions: { [peer]: { state: "verified" } } } });
        window.api.post.mockResolvedValueOnce({ data: { result: { state: "submitted" } } });
        await button("Log out").trigger("click");
        await flushPromises();
        await wrapper.setProps({ snapshot: { ...snapshot } });
        expect(window.api.post).toHaveBeenCalledTimes(2);
        await wrapper.setProps({ visit: "second" });
        await flushPromises();
        expect(window.api.post).toHaveBeenCalledTimes(3);
        expect(window.api.post.mock.calls[2][0]).toBe("/api/v1/meshcore/repeater-auto-login");
    });

    it("pings a repeater without a saved or verified login", async () => {
        setup(2);
        const snapshot = { ...wrapper.props("snapshot"), connection_id: "current" };
        window.api.post.mockResolvedValueOnce({ data: { result: { state: "no_saved_password" } } });
        await wrapper.setProps({ snapshot });
        await flushPromises();
        expect(button("Request status").attributes("disabled")).toBeDefined();
        window.api.post.mockResolvedValueOnce({
            data: {
                result: {
                    state: "route_received",
                    out_hops: 0,
                    in_hops: 0,
                },
            },
        });
        await button("Ping repeater").trigger("click");
        await flushPromises();
        expect(window.api.post).toHaveBeenLastCalledWith(
            "/api/v1/meshcore/node-route",
            { peer, expected_owner: owner },
            { timeout: 150000 }
        );
        expect(wrapper.text()).toContain("Direct connection");
    });

    it("reflects backend room login and does not duplicate it on opening or reconnect", async () => {
        setup();
        const connected = { ...wrapper.props("snapshot"), radio_id: "travel", connection_id: "first" };
        await wrapper.setProps({ snapshot: connected });
        await button("Access").trigger("click");
        expect(wrapper.text()).toContain("Saved room passwords sign in automatically");
        await wrapper.setProps({
            snapshot: { ...connected, node_sessions: { [peer]: { state: "verified" } } },
        });
        expect(wrapper.text()).toContain("Member login verified");
        expect(window.api.post).not.toHaveBeenCalled();
        window.api.post.mockResolvedValueOnce({ data: { result: { state: "submitted" } } });
        await button("Log out").trigger("click");
        await flushPromises();
        await wrapper.setProps({ snapshot: { ...connected, connection_id: "second" } });
        expect(window.api.post).toHaveBeenCalledTimes(1);
        expect(window.api.post.mock.calls[0][0]).toBe("/api/v1/meshcore/node-logout");
    });
    it("keeps the selected tab on refreshed snapshots and resets it for a different radio", async () => {
        setup();
        const snapshot = { ...wrapper.props("snapshot"), radio_id: "first" };
        await wrapper.setProps({ snapshot });
        for (const [tab, panel] of [
            ["Status", "Node status"],
            ["Access", "Node access"],
            ["Manage", "Manage node"],
        ]) {
            await button(tab).trigger("click");
            await wrapper.setProps({ node: { ...wrapper.props("node") }, snapshot: { ...snapshot, messages: [] } });
            expect(button(tab).attributes("aria-pressed")).toBe("true");
            expect(wrapper.find(`[aria-label="${panel}"]`).isVisible()).toBe(true);
        }
        await wrapper.setProps({ snapshot: { ...snapshot, radio_id: "second" } });
        expect(button("Messages").attributes("aria-pressed")).toBe("true");
    });
    it("keeps a room draft across tab changes and exposes admin login without sending anything", async () => {
        setup();
        await wrapper.setProps({
            snapshot: { owner, connected: true, messages: [], node_sessions: { [peer]: { state: "verified" } } },
        });
        await wrapper.find("textarea").setValue("Draft for later");
        await button("Manage").trigger("click");
        expect(wrapper.find('[aria-label="Manage node"]').text()).toContain("Administrator access required");
        await button("Open Access").trigger("click");
        expect(wrapper.find('[aria-label="Node access"]').isVisible()).toBe(true);
        await button("Messages").trigger("click");
        expect(wrapper.find("textarea").element.value).toBe("Draft for later");
        expect(window.api.post).not.toHaveBeenCalled();
    });
    it("updates saved author names reactively and clears them when the active identity changes", async () => {
        setup();
        const message = {
            id: "author-post",
            peer,
            text: "Hello room",
            direction: "in",
            created: 1,
            payload: JSON.stringify({ event: { txt_type: 2, signature: "abcd1234" } }),
        };
        const snapshot = {
            owner,
            connected: true,
            messages: [message],
            contacts: [{ peer: "abcd1234" + "11".repeat(28), name: "Alice" }],
        };
        await wrapper.setProps({ snapshot });
        expect(wrapper.find("article").text()).toContain("Alice");
        expect(wrapper.find("article").text()).toContain("abcd1234 · contact match");
        await wrapper.setProps({ snapshot: { ...snapshot, contacts: [{ ...snapshot.contacts[0], name: "Alicia" }] } });
        expect(wrapper.find("article").text()).toContain("Alicia");
        await wrapper.setProps({ snapshot: { ...snapshot, owner: "ee".repeat(32), contacts: [] } });
        expect(wrapper.find("article").text()).toContain("Author abcd1234");
        expect(wrapper.find("article").text()).not.toContain("Alice");
    });
});
