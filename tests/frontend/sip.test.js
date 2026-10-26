import { beforeEach, afterEach, expect, it, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import {
    HOIP_DEFAULTS,
    sipState,
    sipContacts,
    saveSipContact,
    deleteSipContact,
    sipContactKey,
    sipCommand,
} from "../../meshchatnext/src/frontend/js/sip";
import SipPhone from "../../meshchatnext/src/frontend/components/sip/SipPhone.vue";
import SipContactLink from "../../meshchatnext/src/frontend/components/sip/SipContactLink.vue";
vi.mock("vue-router", () => ({ useRoute: () => ({ query: {} }) }));
beforeEach(() => {
    localStorage.clear();
    sipContacts.splice(0);
    Object.assign(sipState, {
        available: false,
        state: "unavailable",
        accounts: [],
        selected: "",
        registered: false,
        call_state: "idle",
        error: "",
    });
});
afterEach(() => {
    delete window.MeshchatNextAndroid;
    vi.useRealTimers();
});
it("ships a server preset with no account or secret and defaults secure saving on", () => {
    expect(HOIP_DEFAULTS).toEqual({
        host: "premium.hamsoverip.com",
        port: 5160,
        network: "wifi_mobile",
        allowed_networks: ["wifi", "mobile"],
        save_password: true,
    });
    expect(sipState.accounts).toEqual([]);
    expect(localStorage.length).toBe(0);
});
it("keeps SIP contacts separate until an explicit link and supports unlink/removal", async () => {
    const row = saveSipContact({ name: "Test", address: "123456" });
    const contact = { id: 12, remote_identity_hash: "a".repeat(32) };
    const wrapper = mount(SipContactLink, { props: { contact }, global: { mocks: { $router: { push: vi.fn() } } } });
    expect(wrapper.text()).not.toContain("Call via SIP");
    await wrapper.find("button").trigger("click");
    await wrapper.find("select").setValue(row.id);
    await wrapper.find("form").trigger("submit");
    expect(sipContacts[0].linked_contact).toBe(sipContactKey(contact));
    expect(wrapper.text()).toContain("Call via SIP");
    await wrapper
        .findAll("button")
        .find((b) => b.text() === "Unlink SIP")
        .trigger("click");
    expect(sipContacts[0].linked_contact).toBe("");
    deleteSipContact(row.id);
    expect(JSON.parse(localStorage.getItem("meshchat-next.sip.contacts.v1"))).toEqual([]);
    wrapper.unmount();
});
it("rejects contact addresses that inject SIP headers", () => {
    expect(() => saveSipContact({ name: "Test", address: "sip:a@host?Subject=bad" })).toThrow();
});
it("shows native save failures without clearing the account form or password", async () => {
    let status = { available: true, state: "disconnected", accounts: [], call_state: "idle" };
    window.MeshchatNextAndroid = {
        sipStatus: () => JSON.stringify(status),
        sipCommand: () => {
            status = { ...status, last_request: "request", request_error: "Check the extension, server and port" };
            return JSON.stringify({ ok: true, request_id: "request" });
        },
    };
    const wrapper = mount(SipPhone, { props: { mode: "settings" } });
    await flushPromises();
    await wrapper
        .findAll("button")
        .find((b) => b.text() === "Add account")
        .trigger("click");
    const form = wrapper.findAll("form").find((f) => f.find('[autocomplete="username"]').exists());
    const inputs = form.findAll("input");
    await inputs.find((i) => i.attributes("autocomplete") === "username").setValue("bad;user");
    await inputs.find((i) => i.attributes("type") === "password").setValue("fixture-password");
    await form.trigger("submit");
    await flushPromises();
    expect(wrapper.text()).toContain("Check the extension, server and port");
    expect(wrapper.find('input[type="password"]').element.value).toBe("fixture-password");
    expect(localStorage.length).toBe(0);
    wrapper.unmount();
});
it("waits for native acknowledgement and propagates errors", async () => {
    window.MeshchatNextAndroid = {
        sipStatus: () => JSON.stringify({ last_request: "req", request_error: "No allowed network" }),
        sipCommand: () => JSON.stringify({ ok: true, request_id: "req" }),
    };
    await expect(sipCommand("connect", { id: "fixture" })).rejects.toThrow("No allowed network");
});

it("offers independent Wi-Fi/mobile choices and hides unavailable I2P", async () => {
    window.MeshchatNextAndroid = {
        sipStatus: () =>
            JSON.stringify({
                available: true,
                enabled: false,
                state: "disconnected",
                accounts: [],
                call_state: "idle",
                i2p_available: false,
            }),
    };
    const wrapper = mount(SipPhone, { props: { mode: "settings" } });
    await flushPromises();
    await wrapper
        .findAll("button")
        .find((b) => b.text() === "Add account")
        .trigger("click");
    const labels = wrapper.findAll("fieldset label");
    expect(labels.map((l) => l.text())).toEqual(["Wi-Fi", "Mobile data"]);
    expect(labels.every((l) => l.find("input").element.checked)).toBe(true);
    await labels[1].find("input").setValue(false);
    expect(labels[0].find("input").element.checked).toBe(true);
    expect(wrapper.text()).not.toContain("I2P · compatible voice gateway required");
    wrapper.unmount();
});

it("keeps account forms out of Telephone and reconnects the active account explicitly", async () => {
    Object.assign(sipState, {
        available: true,
        registered: false,
        state: "disconnected",
        selected: "fixture",
        accounts: [{ id: "fixture", extension: "123" }],
    });
    window.MeshchatNextAndroid = {
        sipStatus: () => JSON.stringify({ ...sipState }),
        sipCommand: vi.fn(() => JSON.stringify({ ok: true })),
    };
    const wrapper = mount(SipPhone, { global: { stubs: { RouterLink: true } } });
    expect(wrapper.text()).toContain("Disconnected");
    expect(wrapper.find('[autocomplete="username"]').exists()).toBe(false);
    await wrapper
        .findAll("button")
        .find((button) => button.text() === "Reconnect")
        .trigger("click");
    expect(JSON.parse(window.MeshchatNextAndroid.sipCommand.mock.calls[0][0])).toEqual({
        op: "connect",
        id: "fixture",
    });
    wrapper.unmount();
});

it("explains unsupported Android versions without exposing account controls", async () => {
    window.MeshchatNextAndroid = {
        sipStatus: () =>
            JSON.stringify({
                available: false,
                state: "unavailable",
                accounts: [],
                error: "SIP calling requires Android 9 or later",
            }),
    };
    const wrapper = mount(SipPhone, { props: { mode: "settings" } });
    await flushPromises();
    expect(wrapper.text()).toContain("SIP calling requires Android 9 or later");
    expect(wrapper.text()).not.toContain("Add account");
    wrapper.unmount();
});
