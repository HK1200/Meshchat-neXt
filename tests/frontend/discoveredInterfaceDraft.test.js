import { beforeEach, describe, expect, it, vi } from "vitest";
import {
    stageDiscoveredInterfaceDraft,
    takeDiscoveredInterfaceDraft,
} from "../../meshchatnext/src/frontend/js/discoveredInterfaceDraft.js";

describe("private discovery draft transfer", () => {
    beforeEach(() => {
        takeDiscoveredInterfaceDraft();
        sessionStorage.clear();
        vi.restoreAllMocks();
    });

    it("preserves credentials and coordinates for the editor without persisting them", () => {
        const write = vi.spyOn(Storage.prototype, "setItem");
        const draft = {
            name: "Private fixture",
            passphrase: "fixture-passphrase",
            config_entry: "fixture config",
            latitude: 12.34,
            longitude: 56.78,
        };
        stageDiscoveredInterfaceDraft(draft);
        draft.name = "changed later";
        expect(write).not.toHaveBeenCalled();
        expect(sessionStorage.length).toBe(0);
        expect(takeDiscoveredInterfaceDraft()).toEqual({ ...draft, name: "Private fixture" });
        expect(takeDiscoveredInterfaceDraft()).toBeNull();
    });

    it("removes the legacy entry without reading or reusing it", () => {
        sessionStorage.setItem("meshchatnext.discoveredInterfacePrefill", "legacy draft fixture");
        const read = vi.spyOn(Storage.prototype, "getItem");
        stageDiscoveredInterfaceDraft({ name: "Current fixture" });
        expect(read).not.toHaveBeenCalled();
        expect(sessionStorage.length).toBe(0);
        expect(takeDiscoveredInterfaceDraft()).toEqual({ name: "Current fixture" });
    });

    it("works when browser storage access is denied", () => {
        vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
            throw new Error("storage unavailable");
        });
        stageDiscoveredInterfaceDraft({ name: "Current fixture" });
        expect(takeDiscoveredInterfaceDraft()).toEqual({ name: "Current fixture" });
        expect(takeDiscoveredInterfaceDraft()).toBeNull();
    });
});
