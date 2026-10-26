import { it, expect, vi } from "vitest";
import { mount } from "@vue/test-utils";
import MapPage from "../../meshchatnext/src/frontend/components/map/MapPage.vue";
import Offline from "../../meshchatnext/src/frontend/components/map/internal/MapOfflinePanel.vue";
import XYZ from "ol/source/XYZ";

it.each([true, false])("keeps global context beneath regional detail with caching=%s", async (cachingEnabled) => {
    const ctx = {
        tileServerUrl: "",
        offlineEnabled: true,
        cachingEnabled,
        metadata: { "meshchatnext:world_maxzoom": "4" },
        usesOfflineMbtilesRaster: () => true,
        getOfflineMbtilesTopSource: vi.fn(() => new XYZ({})),
        getOfflineRasterCacheOnlySource: vi.fn(() => new XYZ({})),
    };
    const group = await MapPage.methods.buildBaseMapLayer.call(ctx);
    expect(group.getLayers().getLength()).toBe(cachingEnabled ? 3 : 2);
    expect(ctx.getOfflineMbtilesTopSource.mock.calls).toEqual([[4], []]);
    if (cachingEnabled) expect(ctx.getOfflineRasterCacheOnlySource).toHaveBeenCalledWith(true);
});
it("cached street detail stays transparent on misses and can use higher zooms", async () => {
    const ctx = {
        offlineMbtilesZoomRange: () => ({ minZoom: 0, maxZoom: 9 }),
        tryApplyCachedRasterTilesOnly: vi.fn().mockResolvedValue(false),
        applyRasterPlaceholderTile: vi.fn().mockResolvedValue(),
    };
    const source = MapPage.methods.getOfflineRasterCacheOnlySource.call(ctx, true);
    expect(source.getTileGrid().getMaxZoom()).toBe(22);
    const tile = {};
    await source.getTileLoadFunction()(tile, "local-tile");
    expect(ctx.applyRasterPlaceholderTile).toHaveBeenCalledWith(tile, "transparent");
});
it("sanitizes offline attribution and keeps the optional download explicit", () => {
    const attribution = MapPage.methods.offlineAttribution.call({
        metadata: {
            attribution:
                '<a href="https://www.openstreetmap.org/copyright">OSM</a><img src=x onerror=alert(1)><script>bad()</script>',
        },
    });
    expect(attribution).toContain("https://www.openstreetmap.org/copyright");
    expect(attribution).not.toMatch(/script|onerror|<img/);
    const wrapper = mount(Offline, { global: { mocks: { $t: (key) => key } } });
    const link = wrapper.get("a");
    expect(link.attributes("href")).toBe(
        "https://github.com/hk1200/Meshchat-neXt/releases/download/v0.1.0/MeshchatNext-PNW-SouthernBC-detail.mbtiles"
    );
    expect(wrapper.text()).toContain("Optional zoom-12");
    wrapper.unmount();
});

it("opens offline map management rather than general map settings", () => {
    const ctx = { isMapToolsOpen: false, mapToolsTab: "discover", isSettingsOpen: false };
    MapPage.methods.openOfflineMaps.call(ctx);
    expect(ctx.isMapToolsOpen).toBe(true);
    expect(ctx.mapToolsTab).toBe("offline");
    expect(ctx.isSettingsOpen).toBe(false);
});
