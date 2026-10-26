import { mount, flushPromises } from "@vue/test-utils";
import { describe, it, expect, vi, afterEach } from "vitest";
import MeshCoreNodeSession from "../../meshchatnext/src/frontend/components/meshcore/MeshCoreNodeSession.vue";
const owner = "a1".repeat(32),
    peer = "b2".repeat(32);
let wrapper;
afterEach(() => {
    wrapper?.unmount();
    vi.restoreAllMocks();
});
function setup(kind = 3) {
    window.api = { post: vi.fn().mockResolvedValue({ data: { result: { state: "verified", is_admin: false } } }) };
    wrapper = mount(MeshCoreNodeSession, {
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
        await wrapper.find("select").setValue("reboot");
        expect(button("Run server action").attributes("disabled")).toBeDefined();
        await wrapper.find('input[type="checkbox"]').setValue(true);
        window.api.post.mockResolvedValueOnce({ data: { result: { state: "submitted", text: "Restart submitted" } } });
        await button("Run server action").trigger("submit");
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

    it("shows one recovery error and reconnects only MeshCore after an admin timeout", async () => {
        setup();
        const snapshot = {
            owner,
            connected: true,
            messages: [],
            node_sessions: { [peer]: { state: "verified", is_admin: true } },
        };
        await wrapper.setProps({ snapshot });
        window.api.post.mockResolvedValueOnce({ data: { result: { state: "uncertain" } } });
        await button("Run server action").trigger("submit");
        await flushPromises();
        expect(wrapper.findAll('[role="alert"]')).toHaveLength(1);
        expect(button("Reconnect MeshCore")).toBeDefined();
        window.api.get = vi.fn().mockResolvedValue({
            data: { connection: { kind: "ble", target: "radio" }, receiving: true, auto_reconnect: true },
        });
        window.api.post.mockResolvedValue({ data: {} });
        await button("Reconnect MeshCore").trigger("click");
        await flushPromises();
        expect(window.api.post).toHaveBeenCalledWith("/api/v1/meshcore/disconnect", {});
        expect(window.api.post).toHaveBeenCalledWith(
            "/api/v1/meshcore/connect",
            { kind: "ble", target: "radio", receive: true, auto_reconnect: true },
            { timeout: 150000 }
        );
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
        await wrapper.find("select").setValue("set-room-password");
        const value = wrapper.find('[aria-label="Administrator setting value"]');
        const confirm = wrapper.find('[aria-label="Confirm room password"]');
        expect(value.attributes("type")).toBe("password");
        await value.setValue("temporary");
        await confirm.setValue("different");
        await wrapper.find('input[type="checkbox"]').setValue(true);
        expect(button("Run server action").attributes("disabled")).toBeDefined();
        await confirm.setValue("temporary");
        expect(button("Run server action").attributes("disabled")).toBeUndefined();
        let finish;
        window.api.post.mockImplementationOnce(
            () =>
                new Promise((resolve) => {
                    finish = resolve;
                })
        );
        await button("Run server action").trigger("submit");
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
        expect(button("Run server action").attributes("disabled")).toBeDefined();
        await wrapper.setProps({ node: { peer, kind: 2, name: "Repeater" } });
        expect(wrapper.findAll("option").some((x) => x.element.value === "set-room-password")).toBe(false);
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
        await button("Run server action").trigger("submit");
        await flushPromises();
        expect(wrapper.findAll('[role="alert"]')).toHaveLength(1);
        await wrapper.setProps({ snapshot: { ...snapshot, connection_id: "second" } });
        expect(wrapper.findAll('[role="alert"]')).toHaveLength(0);
        expect(button("Run server action").attributes("disabled")).toBeUndefined();
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
        await button("Run server action").trigger("submit");
        await flushPromises();
        expect(wrapper.text()).toContain("The app rejected this request");
        expect(button("Reconnect MeshCore")).toBeUndefined();
        expect(button("Run server action").attributes("disabled")).toBeUndefined();
    });
});
