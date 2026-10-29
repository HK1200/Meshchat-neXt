import { describe, it, expect, vi } from "vitest";
import App from "../../meshchatnext/src/frontend/components/App.vue";

describe("sidebar destination dismissal", () => {
    function click(tag = "a", overrides = {}) {
        const element = document.createElement(tag);
        if (tag === "a") element.href = "#/archives";
        const vm = { isSidebarOpen: true, isSidebarNavEditing: false, $nextTick: (fn) => fn() };
        App.methods.onSidebarDestinationClick.call(vm, { target: element, button: 0, ...overrides });
        return vm;
    }
    it("closes for a destination including the already selected page", () => {
        expect(click().isSidebarOpen).toBe(false);
    });
    it("waits for navigation so the route watcher can preserve Back to sidebar", () => {
        let navigated;
        const remove = vi.fn();
        const link = document.createElement("a");
        link.href = "#/archives";
        const vm = {
            isSidebarOpen: true,
            $nextTick: (fn) => fn(),
            $router: {
                afterEach: (fn) => {
                    navigated = fn;
                    return remove;
                },
            },
        };
        App.methods.onSidebarDestinationClick.call(vm, { target: link, button: 0 });
        expect(vm.isSidebarOpen).toBe(true);
        navigated();
        expect(vm.isSidebarOpen).toBe(false);
        expect(remove).toHaveBeenCalledOnce();
    });
    it("keeps expandable sections open", () => {
        expect(click("button").isSidebarOpen).toBe(true);
    });
    it("keeps modified clicks open", () => {
        expect(click("a", { ctrlKey: true }).isSidebarOpen).toBe(true);
    });
    it("does not dismiss the sidebar during reordering", () => {
        const vm = { isSidebarOpen: true, isSidebarNavEditing: true, $nextTick: vi.fn() };
        App.methods.onSidebarDestinationClick.call(vm, { button: 0 });
        expect(vm.$nextTick).not.toHaveBeenCalled();
    });
});
