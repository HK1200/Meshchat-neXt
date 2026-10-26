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

for (const viewport of [
    { width: 812, height: 375 },
    { width: 640, height: 360 },
]) {
    test.describe(`populated MeshCore landscape ${viewport.width}`, () => {
        test.use({ isMobile: true, hasTouch: true, viewport });
        test.beforeAll(async ({ request }) => {
            await seedUiSimulatedData(request);
        });
        for (const kind of ["channel", "direct"]) {
            test(`${kind} composer, attachments and short keyboard viewport`, async ({ page, baseURL }) => {
                const owner = "a1".repeat(32),
                    peer = "b2".repeat(32),
                    channel = "c7".repeat(32);
                const rows = [
                    {
                        id: "layout-in",
                        direction: "in",
                        text: "Example incoming message",
                        created: 1,
                        state: "received",
                    },
                    {
                        id: "layout-out",
                        direction: "out",
                        text: "Example outgoing message",
                        created: 2,
                        state: "accepted",
                        heard_repeats: 1,
                    },
                ];
                await page.route("**/api/v1/meshcore/**", async (route) => {
                    if (new URL(route.request().url()).pathname.endsWith("/meshcore/ui")) {
                        await route.fulfill({
                            json: {
                                result: {
                                    available: true,
                                    connected: true,
                                    selected: true,
                                    owner,
                                    profile_name: "Example station",
                                    contacts: [{ peer, name: "Example peer" }],
                                    channels: [{ channel_id: channel, slot: 1, name: "#example", kind: "public" }],
                                    messages: rows,
                                    channel_messages: rows.map((row) => ({ ...row, channel_id: channel })),
                                },
                            },
                        });
                    } else if (route.request().method() !== "GET") await route.fulfill({ json: { result: {} } });
                    else await route.continue();
                });
                const path = kind === "channel" ? `/meshcore/channels/${channel}` : `/messages?meshcore=${peer}`;
                await page.goto(`${baseURL}/#${path}`);
                const chat = page.locator("[data-meshcore-chat]");
                const compose = chat.locator("[data-meshcore-compose] textarea");
                await expect(compose).toBeVisible();
                await compose.fill("Keep this draft");
                const list = chat.locator(
                    kind === "channel" ? '[aria-label="Channel messages"]' : '[aria-label="Messages"]'
                );
                expect((await list.boundingBox()).height).toBeGreaterThanOrEqual(60);
                const send = chat.getByRole("button", { name: "Send via MeshCore", exact: true });
                await expect(send).toBeInViewport();
                await chat.getByRole("button", { name: "Photo", exact: true }).click();
                const dialog = page.getByRole("dialog");
                await expect(dialog).toBeVisible();
                await page.setViewportSize({ width: viewport.height, height: viewport.width });
                await expect(dialog).toBeVisible();
                await page.setViewportSize(viewport);
                await dialog.evaluate((el) => el.dispatchEvent(new CustomEvent("app-back", { bubbles: true })));
                await expect(dialog).toHaveCount(0);
                await expect(compose).toHaveValue("Keep this draft");
                await page.setViewportSize({ width: viewport.width, height: 220 });
                await send.scrollIntoViewIfNeeded();
                await expect(send).toBeInViewport();
                await expect(compose).toHaveValue("Keep this draft");
            });
        }
    });
}
