const { test, expect } = require("@playwright/test");
const { seedUiSimulatedData } = require("./seed");
const { waitForBootReady } = require("./ready");

for (const viewport of [
    { width: 812, height: 375 },
    { width: 640, height: 360 },
]) {
    test.describe(`phone landscape ${viewport.width}x${viewport.height}`, () => {
        test.use({ isMobile: true, hasTouch: true, viewport, deviceScaleFactor: 2 });
        test.beforeAll(async ({ request }) => {
            await seedUiSimulatedData(request);
        });
        for (const path of [
            "/messages",
            "/contacts",
            "/settings/meshcore",
            "/settings/reticulum",
            "/meshcore/channels",
            "/meshcore/nodes",
            "/call",
            "/map",
            "/tutorial?setupStep=meshcore",
        ]) {
            test(`content stays within viewport: ${path}`, async ({ page, baseURL }, testInfo) => {
                await page.goto(`${baseURL}/#${path}`);
                await waitForBootReady(page);
                await expect(page.locator("[data-app-menu-toggle]")).toBeVisible();
                await page.waitForTimeout(500);
                const dimensions = await page.evaluate(() => {
                    const main = [...document.querySelectorAll("main")].at(-1);
                    const rect = main?.getBoundingClientRect();
                    return {
                        width: window.innerWidth,
                        height: window.innerHeight,
                        scrollWidth: document.documentElement.scrollWidth,
                        mainBottom: rect?.bottom,
                        mainHeight: rect?.height,
                    };
                });
                expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.width + 1);
                expect(dimensions.mainBottom).toBeLessThanOrEqual(dimensions.height + 1);
                if (!path.startsWith("/tutorial")) expect(dimensions.mainHeight).toBeGreaterThan(100);
                else {
                    const setup = page.getByTestId("setup-scroll");
                    await expect(setup).toBeVisible();
                    await setup.evaluate((el) => {
                        el.scrollTop = el.scrollHeight;
                    });
                    expect(await setup.evaluate((el) => el.scrollTop)).toBeGreaterThan(0);
                }
                if (path === "/map") {
                    await page.getByRole("button", { name: "Offline maps", exact: true }).last().click();
                    await expect(page.getByRole("button", { name: /Download and use regional detail/ })).toBeAttached();
                    await page
                        .getByRole("button", { name: /Download and use regional detail/ })
                        .scrollIntoViewIfNeeded();
                    await expect(
                        page.getByRole("button", { name: /Download and use regional detail/ })
                    ).toBeInViewport();
                }
                await testInfo.attach("landscape", { body: await page.screenshot(), contentType: "image/png" });
            });
        }
    });
}
