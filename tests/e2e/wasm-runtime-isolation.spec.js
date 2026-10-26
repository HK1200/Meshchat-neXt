// SPDX-License-Identifier: 0BSD
const { test, expect } = require("@playwright/test");
const { prepareE2eSession } = require("./helpers");
const { waitForBootReady } = require("../ui/ready");

test("Micron, map, and visualizer retain their own verified Go runtimes", async ({ page, request }) => {
    await prepareE2eSession(request);
    await page.goto("/#/messages");
    await waitForBootReady(page);
    const loaded = await page.evaluate(async () => {
        const [micron, geo, visualiser] = await Promise.all([
            import("/js/MicronWasmLoader.js"),
            import("/js/GeoWasmLoader.js"),
            import("/js/VisualiserWasmLoader.js"),
        ]);
        return Promise.all([micron.preloadNomadMicronWasm(), geo.preloadGeoWasm(), visualiser.preloadVisualiserWasm()]);
    });
    expect(loaded).toEqual([true, true, true]);
});
