// SPDX-License-Identifier: 0BSD
const { expect } = require("@playwright/test");
const { waitForBootReady } = require("../ui/ready");

async function exerciseSidebarDestinationDismissal({ page, baseURL }) {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.route("**/*", (route) => {
        const url = new URL(route.request().url());
        return ["127.0.0.1", "localhost"].includes(url.hostname) || ["data:", "blob:"].includes(url.protocol)
            ? route.continue()
            : route.abort();
    });
    await page.goto(`${baseURL.replace(/\/$/, "")}/`, { waitUntil: "domcontentloaded" });
    await waitForBootReady(page);
    const setup = page
        .getByRole("dialog")
        .filter({ has: page.getByRole("heading", { name: "Set up Meshchat neXt", exact: true }) });
    await setup.waitFor({ state: "visible", timeout: 5000 }).catch(() => {});
    if (await setup.isVisible()) await setup.getByRole("button", { name: "Set up later", exact: true }).click();
    const changes = page
        .getByRole("dialog")
        .filter({ has: page.getByRole("heading", { name: "What's New", exact: true }) });
    await changes.waitFor({ state: "visible", timeout: 5000 }).catch(() => {});
    if (await changes.isVisible()) {
        await changes.getByRole("checkbox", { name: "Do not show again for this version", exact: true }).check();
        await changes.getByRole("button", { name: "Close", exact: true }).last().click();
    }
    const sidebar = page.getByTestId("app-sidebar");
    if ((await sidebar.getAttribute("data-open")) !== "true") await page.locator("[data-app-menu-toggle]").click();
    await expect(sidebar).toHaveAttribute("data-open", "true");
    const contacts = page.getByTestId("sidebar-nav").getByRole("link", { name: "Contacts", exact: true });
    await contacts.click();
    await expect(page).toHaveURL(/#\/contacts$/);
    await expect(sidebar).toHaveAttribute("data-open", "false");
    await page.evaluate(() => window.meshchatHandleBack());
    await expect(page).toHaveURL(/#\/contacts$/);
    await expect(sidebar).toHaveAttribute("data-open", "true");
    await contacts.click();
    await expect(page).toHaveURL(/#\/contacts$/);
    await expect(sidebar).toHaveAttribute("data-open", "false");
}

module.exports = { exerciseSidebarDestinationDismissal };
