import { afterEach, describe, expect, it, vi } from "vitest";
import { handleAppBack, installAndroidBackNavigation, navigateAppBack } from "../../meshchatnext/src/frontend/js/androidBackNavigation";

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

it("returns a MeshCore channel to its manager when no visible back control exists",()=>{
 const r=router("meshcore-channels",{}, {channelId:"a1".repeat(32)});expect(handleAppBack(r)).toBe(true);expect(r.push).toHaveBeenCalledWith({name:"meshcore-channels"});
});


it("returns a captured channel route map to its channel, including direct opens", () => {
    const r = router("map", {mcMessage:"one",mcTarget:"a1".repeat(32),mcKind:"channel"});
    expect(handleAppBack(r)).toBe(true);
    expect(r.push).toHaveBeenCalledWith({name:"meshcore-channels",params:{channelId:"a1".repeat(32)}});
});
it("returns a captured DM map to the correct MeshCore conversation", () => {
    const r = router("map", {mcMessage:"one",mcTarget:"b2".repeat(32),mcKind:"direct"});
    navigateAppBack(r);
    expect(r.push).toHaveBeenCalledWith({name:"messages",query:{meshcore:"b2".repeat(32)}});
});
it("dismisses a mobile sidebar before activating a page Back control", () => {
    document.body.innerHTML = '<div data-app-back-overlay></div><button data-app-back>Back</button>';
    [...document.querySelectorAll("*")].forEach(visible);
    const close=vi.fn(), page=vi.fn();
    document.querySelector("[data-app-back-overlay]").addEventListener("click",close);
    document.querySelector("button").addEventListener("click",page);
    handleAppBack(router("map"));
    expect(close).toHaveBeenCalledOnce();expect(page).not.toHaveBeenCalled();
});
it("dismisses a context menu without navigating", () => {
    document.body.innerHTML = '<div class="context-menu-panel"></div>';
    visible(document.querySelector("div"));
    const listener=vi.fn();window.addEventListener("keydown",listener,{once:true});
    const r=router("map");handleAppBack(r);
    expect(listener).toHaveBeenCalledWith(expect.objectContaining({key:"Escape"}));
    expect(r.push).not.toHaveBeenCalled();
});
it("unwinds app visits without loops and removes its history hook", async () => {
    const {createRouter,createMemoryHistory}=await import("vue-router");
    const r=createRouter({history:createMemoryHistory(),routes:["messages","contacts","map","auth"].map(name=>({path:"/"+name,name,component:{template:"<div/>"}}))});
    await r.push({name:"messages"});const dispose=installAndroidBackNavigation(r,{});
    await r.push({name:"contacts"});await r.push({name:"map"});
    navigateAppBack(r);await new Promise(resolve=>setTimeout(resolve,0));
    expect(r.currentRoute.value.name).toBe("contacts");
    navigateAppBack(r);await new Promise(resolve=>setTimeout(resolve,0));
    expect(r.currentRoute.value.name).toBe("messages");
    expect(navigateAppBack(r)).toBe(false);
    await r.push({name:"auth"});await r.push({name:"map"});
    navigateAppBack(r);await new Promise(resolve=>setTimeout(resolve,0));
    expect(r.currentRoute.value.name).toBe("messages");
    dispose();
});

it("does not resurrect a dismissed map path after an in-place route replacement", () => {
    let hook;
    const r=router("contacts");
    r.currentRoute.value.fullPath="/contacts";
    r.options={history:{state:{position:1}}};
    r.afterEach=fn=>{hook=fn;return ()=>{};};
    r.replace=vi.fn();
    const dispose=installAndroidBackNavigation(r,{});
    r.options.history.state.position=2;
    r.currentRoute.value={name:"map",query:{mcMessage:"one"},fullPath:"/map?mcMessage=one"};
    hook(r.currentRoute.value);
    r.currentRoute.value={name:"map",query:{},fullPath:"/map"};
    hook(r.currentRoute.value);
    navigateAppBack(r);
    expect(r.replace).toHaveBeenCalledWith("/contacts");
    dispose();
});
