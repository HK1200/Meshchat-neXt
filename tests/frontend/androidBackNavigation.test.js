import { afterEach, describe, expect, it, vi } from "vitest";
import {
    handleAppBack,
    installAndroidBackNavigation,
    navigateAppBack,
    rememberSidebarReturn,
    clearSidebarReturn,
} from "../../meshchatnext/src/frontend/js/androidBackNavigation";

const router = (name = "messages", query = {}, params = {}) => ({
    currentRoute: { value: { name, query, params } },
    push: vi.fn(),
});
const visible = (element) => {
    element.getClientRects = () => [{}];
    return element;
};
afterEach(() => {
    document.body.innerHTML = "";
});
describe("Android app back navigation", () => {
    it("clicks the same back action as the app without traversing browser history", () => {
        document.body.innerHTML = "<button data-app-back>Back</button>";
        const button = visible(document.querySelector("button"));
        const clicked = vi.fn();
        button.addEventListener("click", clicked);
        const r = router("messages", { meshcore: "peer" });
        expect(handleAppBack(r)).toBe(true);
        expect(clicked).toHaveBeenCalledOnce();
        expect(r.push).not.toHaveBeenCalled();
    });
    it("ignores hidden and disabled back buttons", () => {
        document.body.innerHTML =
            "<button data-app-back hidden>Hidden</button><button data-app-back disabled>Disabled</button>";
        visible(document.querySelector("[disabled]"));
        const r = router("contacts");
        expect(handleAppBack(r)).toBe(true);
        expect(r.push).toHaveBeenCalledWith({ name: "messages" });
    });
    it("closes the top dialog before navigating the page behind it", () => {
        document.body.innerHTML =
            '<button data-app-back>Page back</button><div role="dialog"><button data-app-back>Close</button></div>';
        [...document.querySelectorAll("*")].forEach(visible);
        const page = vi.fn(),
            close = vi.fn();
        document.querySelector("body > button").addEventListener("click", page);
        document.querySelector('[role="dialog"] button').addEventListener("click", close);
        expect(handleAppBack(router())).toBe(true);
        expect(close).toHaveBeenCalledOnce();
        expect(page).not.toHaveBeenCalled();
    });
    it("cancels confirmation dialogs without accepting the operation", () => {
        document.body.innerHTML =
            '<div role="alertdialog" aria-modal="true"><button data-confirm-cancel>Cancel</button><button>Delete</button></div>';
        [...document.querySelectorAll("*")].forEach(visible);
        const cancelled = vi.fn(),
            confirmed = vi.fn();
        document.querySelector("[data-confirm-cancel]").addEventListener("click", cancelled);
        document.querySelector("button:last-child").addEventListener("click", confirmed);
        const r = router("meshcore-channels");
        expect(handleAppBack(r)).toBe(true);
        expect(cancelled).toHaveBeenCalledOnce();
        expect(confirmed).not.toHaveBeenCalled();
        expect(r.push).not.toHaveBeenCalled();
    });
    it("does not leave a dialog that disallows closing", () => {
        document.body.innerHTML = '<div role="dialog"></div>';
        visible(document.querySelector("div"));
        const r = router("contacts");
        expect(handleAppBack(r)).toBe(true);
        expect(r.push).not.toHaveBeenCalled();
    });
    it("returns node details to the node list", () => {
        const r = router("meshcore-nodes", {}, { peer: "abc" });
        handleAppBack(r);
        expect(r.push).toHaveBeenCalledWith({ name: "meshcore-nodes" });
    });
    it("leaves the root for Android to background, without reopening an old conversation", () => {
        const r = router();
        expect(handleAppBack(r)).toBe(false);
        expect(r.push).not.toHaveBeenCalled();
    });
    it("returns a directly opened conversation to the list", () => {
        const r = router("messages", { meshcore: "abc" });
        expect(handleAppBack(r)).toBe(true);
        expect(r.push).toHaveBeenCalledWith({ name: "messages" });
    });
    it("installs one handler and removes only its own handler", () => {
        const target = {};
        const dispose = installAndroidBackNavigation(router(), target);
        expect(target.meshchatHandleBack()).toBe(false);
        dispose();
        expect(target.meshchatHandleBack).toBeUndefined();
        const disposeOld = installAndroidBackNavigation(router(), target);
        const current = () => true;
        target.meshchatHandleBack = current;
        disposeOld();
        expect(target.meshchatHandleBack).toBe(current);
    });
});

it("returns a MeshCore channel to its manager when no visible back control exists", () => {
    const r = router("meshcore-channels", {}, { channelId: "a1".repeat(32) });
    expect(handleAppBack(r)).toBe(true);
    expect(r.push).toHaveBeenCalledWith({ name: "meshcore-channels" });
});

it("returns a captured channel route map to its channel, including direct opens", () => {
    const r = router("map", { mcMessage: "one", mcTarget: "a1".repeat(32), mcKind: "channel" });
    expect(handleAppBack(r)).toBe(true);
    expect(r.push).toHaveBeenCalledWith({ name: "meshcore-channels", params: { channelId: "a1".repeat(32) } });
});
it("returns a captured DM map to the correct MeshCore conversation", () => {
    const r = router("map", { mcMessage: "one", mcTarget: "b2".repeat(32), mcKind: "direct" });
    navigateAppBack(r);
    expect(r.push).toHaveBeenCalledWith({ name: "messages", query: { meshcore: "b2".repeat(32) } });
});
it("dismisses a mobile sidebar before activating a page Back control", () => {
    document.body.innerHTML = "<div data-app-back-overlay></div><button data-app-back>Back</button>";
    [...document.querySelectorAll("*")].forEach(visible);
    const close = vi.fn(),
        page = vi.fn();
    document.querySelector("[data-app-back-overlay]").addEventListener("click", close);
    document.querySelector("button").addEventListener("click", page);
    handleAppBack(router("map"));
    expect(close).toHaveBeenCalledOnce();
    expect(page).not.toHaveBeenCalled();
});
it("dismisses a context menu without navigating", () => {
    document.body.innerHTML = '<div class="context-menu-panel"></div>';
    visible(document.querySelector("div"));
    const listener = vi.fn();
    window.addEventListener("keydown", listener, { once: true });
    const r = router("map");
    handleAppBack(r);
    expect(listener).toHaveBeenCalledWith(expect.objectContaining({ key: "Escape" }));
    expect(r.push).not.toHaveBeenCalled();
});
it("unwinds app visits without loops and removes its history hook", async () => {
    const { createRouter, createMemoryHistory } = await import("vue-router");
    const r = createRouter({
        history: createMemoryHistory(),
        routes: ["messages", "contacts", "map", "auth"].map((name) => ({
            path: "/" + name,
            name,
            component: { template: "<div/>" },
        })),
    });
    await r.push({ name: "messages" });
    const dispose = installAndroidBackNavigation(r, {});
    await r.push({ name: "contacts" });
    await r.push({ name: "map" });
    navigateAppBack(r);
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(r.currentRoute.value.name).toBe("contacts");
    navigateAppBack(r);
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(r.currentRoute.value.name).toBe("messages");
    expect(navigateAppBack(r)).toBe(false);
    await r.push({ name: "auth" });
    await r.push({ name: "map" });
    navigateAppBack(r);
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(r.currentRoute.value.name).toBe("messages");
    dispose();
});

it("does not resurrect a dismissed map path after an in-place route replacement", () => {
    let hook;
    const r = router("contacts");
    r.currentRoute.value.fullPath = "/contacts";
    r.options = { history: { state: { position: 1 } } };
    r.afterEach = (fn) => {
        hook = fn;
        return () => {};
    };
    r.replace = vi.fn();
    const dispose = installAndroidBackNavigation(r, {});
    r.options.history.state.position = 2;
    r.currentRoute.value = { name: "map", query: { mcMessage: "one" }, fullPath: "/map?mcMessage=one" };
    hook(r.currentRoute.value);
    r.currentRoute.value = { name: "map", query: {}, fullPath: "/map" };
    hook(r.currentRoute.value);
    navigateAppBack(r);
    expect(r.replace).toHaveBeenCalledWith("/contacts");
    dispose();
});

it("closes an expanded in-page view before following route history", () => {
    document.body.innerHTML = "<section data-app-back-scope><button data-app-back>Hide discoveries</button></section>";
    [...document.querySelectorAll("*")].forEach(visible);
    const close = vi.fn();
    document.querySelector("section").addEventListener("app-back", close);
    const r = router("meshcore-nodes");
    handleAppBack(r);
    expect(close).toHaveBeenCalledOnce();
    expect(r.push).not.toHaveBeenCalled();
});
it("closes the topmost modal before a lower page panel or sidebar", () => {
    document.body.innerHTML =
        '<section data-app-back-scope style="z-index:1"></section><div role="dialog" style="z-index:200"><button data-app-back>Cancel</button></div>';
    [...document.querySelectorAll("*")].forEach(visible);
    const page = vi.fn(),
        cancel = vi.fn();
    document.querySelector("section").addEventListener("app-back", page);
    document.querySelector("button").addEventListener("click", cancel);
    handleAppBack(router("map"));
    expect(cancel).toHaveBeenCalledOnce();
    expect(page).not.toHaveBeenCalled();
});
it("keeps repeated visits in chronological order instead of skipping them", async () => {
    const { createRouter, createMemoryHistory } = await import("vue-router");
    const r = createRouter({
        history: createMemoryHistory(),
        routes: ["messages", "contacts", "map", "tools"].map((name) => ({
            path: "/" + name,
            name,
            component: { template: "<div/>" },
        })),
    });
    await r.push("/messages");
    const dispose = installAndroidBackNavigation(r, {});
    for (const path of ["/contacts", "/map", "/contacts", "/tools"]) await r.push(path);
    for (const expected of ["contacts", "map", "contacts", "messages"]) {
        navigateAppBack(r);
        await new Promise((resolve) => setTimeout(resolve, 0));
        expect(r.currentRoute.value.name).toBe(expected);
    }
    expect(navigateAppBack(r)).toBe(false);
    dispose();
});
it("does not reopen a captured map after returning to its channel and manager", async () => {
    const { createRouter, createMemoryHistory } = await import("vue-router");
    const { navigateAppUp } = await import("../../meshchatnext/src/frontend/js/androidBackNavigation");
    const r = createRouter({
        history: createMemoryHistory(),
        routes: [
            { path: "/messages", name: "messages", component: {} },
            { path: "/meshcore/channels/:channelId?", name: "meshcore-channels", component: {} },
            { path: "/map", name: "map", component: {} },
        ],
    });
    await r.push("/messages");
    const dispose = installAndroidBackNavigation(r, {});
    await r.push("/meshcore/channels");
    await r.push("/meshcore/channels/abc");
    await r.push({ name: "map", query: { mcMessage: "one", mcTarget: "abc", mcKind: "channel" } });
    navigateAppBack(r);
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(r.currentRoute.value.params.channelId).toBe("abc");
    navigateAppUp(r, { name: "meshcore-channels" });
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(r.currentRoute.value.fullPath).toBe("/meshcore/channels");
    navigateAppBack(r);
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(r.currentRoute.value.name).toBe("messages");
    dispose();
});
it.each([
    "ping",
    "rncp",
    "rns-filesync",
    "rnsh",
    "rnx",
    "rnstatus",
    "traffic",
    "rnpath",
    "rnpath-trace",
    "rnprobe",
    "translator",
    "bots",
    "forwarder",
    "micron-editor",
    "reticulum-config-editor",
    "mesh-server",
    "paper-message",
    "nearby",
    "sieve-filters",
    "message-blocklist",
    "rnode-flasher",
    "repository-server",
])("uses Tools as the safe direct-entry parent for %s", (name) => {
    const r = router(name);
    navigateAppBack(r);
    expect(r.push).toHaveBeenCalledWith({ name: "tools" });
});

it("page Back links consume a visit so the next Back cannot reopen it", async () => {
    const { createRouter, createMemoryHistory } = await import("vue-router");
    const r = createRouter({
        history: createMemoryHistory(),
        routes: ["messages", "tools", "ping"].map((name) => ({ path: "/" + name, name, component: {} })),
    });
    await r.push("/messages");
    const dispose = installAndroidBackNavigation(r, window);
    await r.push("/tools");
    await r.push("/ping");
    document.body.innerHTML = '<a data-app-back href="#/tools"><span>Tools</span></a>';
    document.querySelector("span").click();
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(r.currentRoute.value.name).toBe("tools");
    navigateAppBack(r);
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(r.currentRoute.value.name).toBe("messages");
    dispose();
});

describe("mobile sidebar return views", () => {
    let dispose;
    afterEach(() => {
        dispose?.();
        dispose = null;
        vi.restoreAllMocks();
    });
    async function setup(useHashHistory = false) {
        const { createRouter, createMemoryHistory, createWebHashHistory } = await import("vue-router");
        const r = createRouter({
            history: useHashHistory ? createWebHashHistory() : createMemoryHistory(),
            routes: [
                ...[
                    "messages",
                    "archives",
                    "contacts",
                    "tools",
                    "map",
                    "feature-settings",
                    "meshcore-nodes",
                    "meshcore-channels",
                    "call",
                ].map((name) => ({ path: "/" + name, name, component: {} })),
                { path: "/archives/:id", name: "archive-detail", component: {} },
            ],
        });
        await r.push("/messages");
        const remove = installAndroidBackNavigation(r, window);
        dispose = () => {
            remove();
            r.options.history.destroy();
        };
        return r;
    }
    it.each([
        "archives",
        "contacts",
        "tools",
        "map",
        "feature-settings",
        "meshcore-nodes",
        "meshcore-channels",
        "call",
    ])("reopens the sidebar once before leaving its %s selection", async (name) => {
        const r = await setup(),
            reopen = vi.fn(() => true);
        await r.push("/" + name);
        rememberSidebarReturn(r, r.currentRoute.value.fullPath, reopen);
        expect(navigateAppBack(r)).toBe(true);
        expect(reopen).toHaveBeenCalledOnce();
        expect(r.currentRoute.value.name).toBe(name);
        navigateAppBack(r);
        await new Promise((resolve) => setTimeout(resolve, 0));
        expect(r.currentRoute.value.name).toBe("messages");
        expect(reopen).toHaveBeenCalledOnce();
    });
    it("returns from a child page before reopening its parent page's sidebar", async () => {
        const r = await setup(),
            reopen = vi.fn(() => true);
        await r.push("/archives");
        rememberSidebarReturn(r, "/archives", reopen);
        await r.push("/archives/one");
        navigateAppBack(r);
        await new Promise((resolve) => setTimeout(resolve, 0));
        expect(r.currentRoute.value.name).toBe("archives");
        expect(reopen).not.toHaveBeenCalled();
        navigateAppBack(r);
        expect(reopen).toHaveBeenCalledOnce();
        expect(r.currentRoute.value.name).toBe("archives");
    });
    it("closes a modal, reopens the drawer, then closes the drawer before leaving the page", async () => {
        const r = await setup();
        await r.push("/archives");
        const reopen = vi.fn(() => {
            document.body.innerHTML = "<div data-app-back-overlay></div>";
            const overlay = visible(document.querySelector("div"));
            overlay.addEventListener("click", () => overlay.remove());
            return true;
        });
        rememberSidebarReturn(r, "/archives", reopen);
        document.body.innerHTML = '<div role="dialog"><button data-app-back>Close</button></div>';
        [...document.querySelectorAll("*")].forEach(visible);
        document.querySelector("button").addEventListener("click", () => document.querySelector("div").remove());
        handleAppBack(r);
        expect(reopen).not.toHaveBeenCalled();
        handleAppBack(r);
        expect(reopen).toHaveBeenCalledOnce();
        handleAppBack(r);
        expect(document.querySelector("[data-app-back-overlay]")).toBeNull();
        expect(r.currentRoute.value.name).toBe("archives");
        handleAppBack(r);
        await new Promise((resolve) => setTimeout(resolve, 0));
        expect(r.currentRoute.value.name).toBe("messages");
    });
    it("uses the same sidebar checkpoint for a clicked app Back button", async () => {
        const r = await setup(),
            reopen = vi.fn(() => true),
            pageBack = vi.fn();
        await r.push("/archives");
        rememberSidebarReturn(r, "/archives", reopen);
        document.body.innerHTML = "<button data-app-back>Back</button>";
        document.querySelector("button").addEventListener("click", pageBack);
        document.querySelector("button").click();
        expect(reopen).toHaveBeenCalledOnce();
        expect(pageBack).not.toHaveBeenCalled();
        expect(r.currentRoute.value.name).toBe("archives");
    });
    it("a clicked page Back closes a local panel before reopening the sidebar", async () => {
        const r = await setup(),
            reopen = vi.fn(() => true);
        await r.push("/archives");
        rememberSidebarReturn(r, "/archives", reopen);
        document.body.innerHTML =
            '<button id="header-back" data-app-back>Back</button><section data-app-back-scope></section>';
        [...document.querySelectorAll("*")].forEach(visible);
        document
            .querySelector("section")
            .addEventListener("app-back", () => document.querySelector("section").remove());
        document.querySelector("#header-back").click();
        expect(document.querySelector("section")).toBeNull();
        expect(reopen).not.toHaveBeenCalled();
        document.querySelector("#header-back").click();
        expect(reopen).toHaveBeenCalledOnce();
        expect(r.currentRoute.value.name).toBe("archives");
    });
    it("a page Back inside the map's root scope dismisses its local view before opening the menu", async () => {
        const r = await setup(),
            reopen = vi.fn(() => true);
        await r.push("/map");
        rememberSidebarReturn(r, "/map", reopen);
        document.body.innerHTML =
            "<section data-app-back-scope><button data-app-back>Back to message</button></section>";
        [...document.querySelectorAll("*")].forEach(visible);
        const section = document.querySelector("section");
        section.addEventListener("app-back", () => section.removeAttribute("data-app-back-scope"));
        document.querySelector("button").click();
        expect(reopen).not.toHaveBeenCalled();
        expect(section.hasAttribute("data-app-back-scope")).toBe(false);
        document.querySelector("button").click();
        expect(reopen).toHaveBeenCalledOnce();
        expect(r.currentRoute.value.name).toBe("map");
    });
    it("retains each sidebar visit independently and survives an in-place URL replacement", async () => {
        const r = await setup(true),
            archives = vi.fn(() => true),
            contacts = vi.fn(() => true);
        await r.push("/archives");
        rememberSidebarReturn(r, "/archives", archives);
        await r.replace("/archives?filter=recent");
        await r.push("/contacts");
        rememberSidebarReturn(r, "/contacts", contacts);
        navigateAppBack(r);
        expect(contacts).toHaveBeenCalledOnce();
        navigateAppBack(r);
        await new Promise((resolve) => setTimeout(resolve, 0));
        expect(r.currentRoute.value.fullPath).toBe("/archives?filter=recent");
        navigateAppBack(r);
        expect(archives).toHaveBeenCalledOnce();
    });
    it("does not reopen a sidebar that the user already opened and closed manually", async () => {
        const r = await setup(),
            reopen = vi.fn(() => true);
        await r.push("/archives");
        rememberSidebarReturn(r, "/archives", reopen);
        clearSidebarReturn(r);
        navigateAppBack(r);
        await new Promise((resolve) => setTimeout(resolve, 0));
        expect(r.currentRoute.value.name).toBe("messages");
        expect(reopen).not.toHaveBeenCalled();
    });
    it("falls back to normal history if the drawer is no longer a mobile view", async () => {
        const r = await setup(),
            reopen = vi.fn(() => false);
        await r.push("/archives");
        rememberSidebarReturn(r, "/archives", reopen);
        navigateAppBack(r);
        await new Promise((resolve) => setTimeout(resolve, 0));
        expect(r.currentRoute.value.name).toBe("messages");
    });
    it("records the actual App route watcher before it closes a mobile drawer", async () => {
        const r = await setup();
        const { watch, nextTick } = await import("vue");
        const { default: App } = await import("../../meshchatnext/src/frontend/components/App.vue");
        vi.spyOn(window, "matchMedia").mockReturnValue({ matches: true });
        const ctx = { $router: r, isSidebarOpen: true, $refs: {} };
        const stop = watch(
            () => r.currentRoute.value,
            (to, from) => App.watch.$route.call(ctx, to, from)
        );
        try {
            await r.push("/archives");
            await nextTick();
            expect(ctx.isSidebarOpen).toBe(false);
            navigateAppBack(r);
            expect(ctx.isSidebarOpen).toBe(true);
            expect(r.currentRoute.value.name).toBe("archives");
        } finally {
            stop();
        }
    });
});
