// SPDX-License-Identifier: 0BSD
import { mount, flushPromises } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import RecipientCallAlerts from "@/components/settings/RecipientCallAlerts.vue";

const route = { provider: "https://alerts.example.invalid", audience: "private test", public_key: "b2".repeat(64) };
const contacts = [
    { id: 1, name: "Family recipient", lxmf_address: "a1".repeat(16) },
    { id: 2, name: "Second recipient", lxmf_address: "a2".repeat(16) },
    { id: 3, name: "SIP only", lxmf_address: null },
];
let wrappers = [];
function section(props = {}, getRoute = async () => null) {
    window.api = {
        get: vi.fn(async (url) => ({
            data: url.endsWith("/contacts")
                ? { contacts }
                : { route: await getRoute(url), public_key: route.public_key },
        })),
        post: vi.fn(async (_url, body) => ({ data: { route: body.route } })),
        delete: vi.fn(async () => ({ data: { route: null } })),
    };
    const wrapper = mount(RecipientCallAlerts, { props, global: { mocks: { $t: (key) => key } } });
    wrappers.push(wrapper);
    return wrapper;
}
async function select(wrapper, id = "1") {
    await flushPromises();
    await wrapper.get('[data-testid="call-alert-contact"]').setValue(id);
    await flushPromises();
}
afterEach(() => {
    wrappers.forEach((wrapper) => wrapper.unmount());
    wrappers = [];
    delete window.api;
    vi.useRealTimers();
});

describe("Optional recipient mailbox alerts", () => {
    it("does not load hidden settings or configure a provider automatically", async () => {
        const wrapper = section({ visible: false });
        await flushPromises();
        expect(window.api.get).not.toHaveBeenCalled();
        await wrapper.setProps({ visible: true });
        await flushPromises();
        expect(
            wrapper
                .findAll("option")
                .map((row) => row.text())
                .join(" ")
        ).not.toContain("SIP only");
        expect(window.api.post).not.toHaveBeenCalled();
        expect(window.api.delete).not.toHaveBeenCalled();
    });
    it("requires explicit valid HTTPS details and normalizes only the selected contact", async () => {
        const wrapper = section();
        await select(wrapper);
        expect(wrapper.get('[data-testid="call-alert-save"]').element.disabled).toBe(true);
        await wrapper.get('[data-testid="call-alert-provider"]').setValue("http://alerts.example.invalid");
        await wrapper.get('[data-testid="call-alert-audience"]').setValue(route.audience);
        expect(wrapper.get('[data-testid="call-alert-save"]').element.disabled).toBe(true);
        await wrapper.get('[data-testid="call-alert-provider"]').setValue(route.provider + "/");
        expect(wrapper.get('[data-testid="call-alert-key-status"]').text()).toBe("call_alerts.verified_identity");
        expect(window.api.post).not.toHaveBeenCalled();
        await wrapper.get('[data-testid="call-alert-save"]').trigger("click");
        await flushPromises();
        expect(window.api.post).toHaveBeenCalledWith("/api/v1/telephone/contacts/1/call-alert-route", { route });
        expect(wrapper.get('[data-testid="call-alert-route-state"]').text()).toBe("call_alerts.on");
    });
    it("requires a verified contact identity without asking users to type a key", async () => {
        const wrapper = section();
        const get = window.api.get;
        window.api.get = vi.fn(async (url) =>
            url.endsWith("/contacts") ? get(url) : { data: { route: null, public_key: null } }
        );
        await select(wrapper);
        await wrapper.get('[data-testid="call-alert-provider"]').setValue(route.provider);
        await wrapper.get('[data-testid="call-alert-audience"]').setValue(route.audience);
        expect(wrapper.get('[data-testid="call-alert-save"]').element.disabled).toBe(true);
        expect(wrapper.get('[data-testid="call-alert-key-status"]').text()).toBe("call_alerts.waiting_identity");
        expect(wrapper.find('input[maxlength="128"]').exists()).toBe(true);
        expect(wrapper.findAll("input").length).toBe(3);
        expect(window.api.post).not.toHaveBeenCalled();
    });
    it("removes only alert details and keeps the saved contact selected", async () => {
        const wrapper = section({}, async () => route);
        await select(wrapper);
        await wrapper.get('[data-testid="call-alert-remove"]').trigger("click");
        await flushPromises();
        expect(window.api.delete).toHaveBeenCalledWith("/api/v1/telephone/contacts/1/call-alert-route");
        expect(wrapper.get('[data-testid="call-alert-contact"]').element.value).toBe("1");
        expect(wrapper.get('[data-testid="call-alert-route-state"]').text()).toBe("call_alerts.off");
        expect(wrapper.get('[data-testid="call-alert-provider"]').element.value).toBe("");
    });
    it("ignores a late response from another contact", async () => {
        let resolveFirst;
        const first = new Promise((resolve) => {
            resolveFirst = resolve;
        });
        const wrapper = section({}, (url) =>
            url.includes("/1/") ? first : Promise.resolve({ ...route, audience: "second" })
        );
        await select(wrapper, "1");
        await select(wrapper, "2");
        await wrapper.get('[data-testid="call-alert-audience"]').setValue("unsaved second");
        resolveFirst(route);
        await flushPromises();
        expect(wrapper.get('[data-testid="call-alert-audience"]').element.value).toBe("unsaved second");
        expect(wrapper.get('[data-testid="call-alert-contact"]').element.value).toBe("2");
    });
    it("preserves unsaved edits while checking current saved consent", async () => {
        const getRoute = vi.fn(async () => null);
        const wrapper = section({}, getRoute);
        await select(wrapper, "1");
        await wrapper.get('[data-testid="call-alert-provider"]').setValue("https://draft.example.invalid");
        await select(wrapper, "2");
        await select(wrapper, "1");
        expect(wrapper.get('[data-testid="call-alert-provider"]').element.value).toBe("https://draft.example.invalid");
        expect(getRoute).toHaveBeenCalledTimes(3);
        expect(window.api.post).not.toHaveBeenCalled();
    });
    it("retries a failed route read without discarding the contact", async () => {
        let fail = true;
        const wrapper = section({}, async () => {
            if (fail) throw new Error("synthetic");
            return route;
        });
        await select(wrapper);
        expect(wrapper.get('[data-testid="call-alert-save"]').element.disabled).toBe(true);
        fail = false;
        await wrapper.get('[data-testid="call-alert-refresh"]').trigger("click");
        await flushPromises();
        expect(wrapper.get('[data-testid="call-alert-provider"]').element.value).toBe(route.provider);
        expect(wrapper.get('[data-testid="call-alert-remove"]').element.disabled).toBe(false);
    });
});
