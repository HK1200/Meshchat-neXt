import { beforeEach, afterEach, expect, it, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { ref } from "vue";
import { createPinia, setActivePinia } from "pinia";
import FirstLaunchSetup from "../../meshchatnext/src/frontend/components/setup/FirstLaunchSetup.vue";
import { appFeatures, normalizeFeatures } from "../../meshchatnext/src/frontend/js/appFeatures";
import { SETUP_DRAFT_KEY } from "../../meshchatnext/src/frontend/js/firstLaunchSetup";
const navigation = vi.hoisted(() => ({ leave: null }));
vi.mock("vue-router", () => ({
    onBeforeRouteLeave: (guard) => {
        navigation.leave = guard;
    },
    useRoute: () => ({ meta: { isPage: true } }),
    useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));
vi.mock("../../meshchatnext/src/frontend/js/meshcoreUi", () => ({
    useMeshCoreUi: () => ({
        snapshot: ref({ available: true, connected: false, owner: null, contacts: [], channels: [] }),
        refresh: vi.fn(),
    }),
}));
vi.mock("../../meshchatnext/src/frontend/js/GlobalEmitter", () => ({ default: { emit: vi.fn() } }));
let wrappers = [];
function mountGuide() {
    const wrapper = mount(FirstLaunchSetup, {
        props: { page: true },
        global: {
            stubs: {
                AppModal: { template: "<div><slot/></div>" },
                LanguageSelector: true,
                MeshCoreSettings: true,
                MeshCoreBackups: true,
                MeshCoreIdentitySettings: true,
                RNodeSetup: true,
                SipPhone: true,
                RouterLink: true,
            },
        },
    });
    wrappers.push(wrapper);
    return wrapper;
}
async function next(wrapper) {
    await wrapper
        .findAll("button")
        .find((button) => button.text() === "Continue")
        .trigger("click");
    await flushPromises();
}
beforeEach(() => {
    localStorage.clear();
    Object.assign(appFeatures, normalizeFeatures(null));
    setActivePinia(createPinia());
    window.api = {
        get: vi.fn(async (path) => ({
            data: path.endsWith("/config")
                ? { config: { display_name: "Existing name" } }
                : path.endsWith("/identities")
                  ? { identities: [{ hash: "b".repeat(32), is_current: true }] }
                  : {},
        })),
        patch: vi.fn(async () => ({ data: { config: { display_name: "Existing name" } } })),
        post: vi.fn(async (path) => ({
            data: path.endsWith("/identity/restore")
                ? { identity: { hash: "a".repeat(32) } }
                : path.endsWith("/identities/switch")
                  ? { hotswapped: true, identity_hash: "a".repeat(32) }
                  : {},
        })),
        delete: vi.fn(),
    };
});
afterEach(() => {
    for (const wrapper of wrappers) wrapper.unmount();
    wrappers = [];
    Object.assign(appFeatures, normalizeFeatures(null));
});
it("starts without connecting or modifying interfaces and skips irrelevant network steps", async () => {
    const wrapper = mountGuide();
    await flushPromises();
    expect(wrapper.text()).toContain("What would you like to use?");
    expect(window.api.post).not.toHaveBeenCalled();
    const checks = wrapper.findAll('input[type="checkbox"]');
    await checks[0].setValue(false);
    await checks[2].setValue(false);
    await next(wrapper);
    expect(wrapper.text()).toContain("Connect your MeshCore client");
    expect(wrapper.find("mesh-core-backups-stub").exists()).toBe(false);
    await wrapper.get("select").setValue("import");
    expect(wrapper.find("mesh-core-backups-stub").attributes("importonly")).toBe("true");
    await next(wrapper);
    expect(wrapper.text()).toContain("Preview and apply your backup first");
    await wrapper.get("select").setValue("keep");
    await next(wrapper);
    expect(wrapper.text()).toContain("Optional photos and voice");
    await next(wrapper);
    expect(wrapper.text()).toContain("Ready to use neXt");
    expect(window.api.post).not.toHaveBeenCalled();
});
it("persists only non-secret draft choices, and retries activation without reimporting or deleting identities", async () => {
    Object.assign(appFeatures, { reticulum: true, meshcore: false, sip: false });
    let fail = true;
    window.api.post.mockImplementation(async (path) => {
        if (path.endsWith("/identity/restore")) return { data: { identity: { hash: "a".repeat(32) } } };
        if (path.endsWith("/identities/switch")) {
            if (fail) throw new Error("activation unavailable");
            return { data: { hotswapped: true } };
        }
        return { data: {} };
    });
    const wrapper = mountGuide();
    await flushPromises();
    await next(wrapper);
    await wrapper.get("select").setValue("base32");
    await wrapper.get("textarea").setValue("synthetic-private-export");
    await next(wrapper);
    expect(wrapper.get('[role="alert"]').text()).toContain("activation unavailable");
    expect(localStorage.getItem(SETUP_DRAFT_KEY)).not.toContain("synthetic-private-export");
    expect(JSON.parse(localStorage.getItem(SETUP_DRAFT_KEY)).pendingIdentity).toBe("a".repeat(32));
    expect(wrapper.find("textarea").exists()).toBe(false);
    fail = false;
    await next(wrapper);
    expect(wrapper.text()).toContain("Connect Reticulum");
    expect(window.api.post.mock.calls.filter(([path]) => path.endsWith("/identity/restore"))).toHaveLength(1);
    expect(window.api.post.mock.calls.filter(([path]) => path.endsWith("/identities/switch"))).toHaveLength(2);
    expect(window.api.delete).not.toHaveBeenCalled();
});
it("allows setup later without adding TCP, changing radio settings or supplying an account", async () => {
    const wrapper = mountGuide();
    await flushPromises();
    await wrapper
        .findAll("button")
        .find((button) => button.text() === "Set up later")
        .trigger("click");
    await flushPromises();
    expect(window.api.post).toHaveBeenCalledWith("/api/v1/app/tutorial/seen");
    expect(window.api.post.mock.calls).toHaveLength(1);
    expect(localStorage.getItem(SETUP_DRAFT_KEY)).toBeNull();
});

it("keeps navigation outside the bounded scroll area so expanded imports cannot hide Continue", async () => {
    const wrapper = mountGuide();
    await flushPromises();
    const scroll = wrapper.get('[data-testid="setup-scroll"]');
    expect(scroll.classes()).toContain("overflow-y-auto");
    expect(scroll.classes()).toContain("min-h-0");
    expect(wrapper.get("footer").classes()).toContain("shrink-0");
    expect(wrapper.get("footer").element.closest('[data-testid="setup-scroll"]')).toBeNull();
});

it("keeps browser back within setup and lets explicit completion leave", async () => {
    const wrapper = mountGuide();
    await flushPromises();
    await next(wrapper);
    expect(wrapper.text()).toContain("Reticulum identity");
    expect(navigation.leave()).toBe(false);
    await flushPromises();
    expect(wrapper.text()).toContain("What would you like to use?");
    expect(navigation.leave()).toBe(false);
    await flushPromises();
    expect(wrapper.text()).toContain("Choose Set up later to leave");
    await wrapper
        .findAll("button")
        .find((button) => button.text() === "Set up later")
        .trigger("click");
    await flushPromises();
    expect(navigation.leave()).toBe(true);
});

it("does not render a second wizard from the global modal on the tutorial page", () => {
    const wrapper = mount(FirstLaunchSetup, { props: { page: false } });
    expect(wrapper.find('[data-testid="setup-scroll"]').exists()).toBe(false);
    wrapper.unmount();
});

it("starts each new setup step at the top rather than inheriting the previous scroll position", async () => {
    const wrapper = mountGuide();
    await flushPromises();
    const scroll = wrapper.get('[data-testid="setup-scroll"]').element;
    scroll.scrollTop = 900;
    await next(wrapper);
    expect(scroll.scrollTop).toBe(0);
    scroll.scrollTop = 700;
    await wrapper
        .findAll("button")
        .find((button) => button.text() === "Back")
        .trigger("click");
    await flushPromises();
    expect(scroll.scrollTop).toBe(0);
});

it("routes button and Android Back to the setup step inside the real persistent dialog", async () => {
    const { installAndroidBackNavigation, handleAppBack } =
        await import("../../meshchatnext/src/frontend/js/androidBackNavigation");
    const rects = vi.spyOn(Element.prototype, "getClientRects").mockReturnValue([{ width: 300, height: 500 }]);
    const router = {
        currentRoute: { value: { name: "messages", fullPath: "/messages" } },
        options: { history: { state: { position: 0 } } },
        afterEach: () => () => {},
    };
    const remove = installAndroidBackNavigation(router, window);
    const wrapper = mount(FirstLaunchSetup, {
        attachTo: document.body,
        props: { page: false },
        global: {
            mocks: { $t: (key) => key },
            stubs: {
                LanguageSelector: true,
                MeshCoreSettings: true,
                MeshCoreBackups: true,
                MeshCoreIdentitySettings: true,
                RNodeSetup: true,
                SipPhone: true,
                RouterLink: true,
            },
        },
    });
    try {
        await wrapper.vm.show();
        await flushPromises();
        const button = (text) => [...document.querySelectorAll("button")].find((b) => b.textContent.trim() === text);
        button("Continue").click();
        await flushPromises();
        expect(document.body.textContent).toContain("2 of 7");
        button("Back").click();
        await flushPromises();
        expect(document.body.textContent).toContain("1 of 7");
        button("Continue").click();
        await flushPromises();
        handleAppBack(router, document);
        await flushPromises();
        expect(document.body.textContent).toContain("1 of 7");
    } finally {
        remove();
        wrapper.unmount();
        rects.mockRestore();
    }
});
