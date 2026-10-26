const { test, expect } = require("@playwright/test");
const { waitForBootReady } = require("../ui/ready");
const {
    PALETTE_PLACEHOLDER,
    dismissMapOnboardingTooltip,
    openCommandPalette,
    prepareE2eSession,
} = require("./helpers");

test.describe("Getting started (tutorial page)", () => {
    test("tutorial route shows welcome copy", async ({ page }) => {
        await page.goto("/#/tutorial");
        await waitForBootReady(page);
        await expect(page).toHaveURL(/#\/tutorial/);
        await expect(page.getByRole("heading", { name: /Welcome to\s*Meshchat neXt/i }).first()).toBeVisible({
            timeout: 30000,
        });
        await expect(page.getByText(/Reticulum and MeshCore/i).first()).toBeVisible({
            timeout: 10000,
        });
    });
});

test.describe("Command palette", () => {
    test.beforeEach(async ({ request }) => {
        await prepareE2eSession(request);
    });

    test("Ctrl+K opens palette with search field", async ({ page }) => {
        await page.goto("/#/messages");
        await waitForBootReady(page);
        await openCommandPalette(page);
        await expect(page.getByPlaceholder(PALETTE_PLACEHOLDER)).toBeVisible();
        await expect(page.getByText("Navigate", { exact: true })).toBeVisible();
    });

    test("palette navigates to Settings via filter and Enter", async ({ page }) => {
        await page.goto("/#/messages");
        await waitForBootReady(page);
        await openCommandPalette(page);
        const input = page.getByPlaceholder(PALETTE_PLACEHOLDER);
        await input.fill("Settings");
        await page.keyboard.press("Enter");
        await expect(page).toHaveURL(/#\/settings/, { timeout: 15000 });
        await expect(page.getByText("Profile", { exact: true }).first()).toBeVisible({ timeout: 20000 });
    });

    test("palette navigates to Documentation via filter and Enter", async ({ page }) => {
        await page.goto("/#/map");
        await waitForBootReady(page);
        await openCommandPalette(page);
        const input = page.getByPlaceholder(PALETTE_PLACEHOLDER);
        await input.fill("Documentation");
        await page.keyboard.press("Enter");
        await expect(page).toHaveURL(/#\/documentation/, { timeout: 15000 });
        await expect(
            page.getByRole("heading", { name: "Getting started with Meshchat neXt", exact: true })
        ).toBeVisible({
            timeout: 20000,
        });
    });

    test("Escape closes command palette", async ({ page }) => {
        await page.goto("/#/messages");
        await waitForBootReady(page);
        await openCommandPalette(page);
        const input = page.getByPlaceholder(PALETTE_PLACEHOLDER);
        await page.keyboard.press("Escape");
        await expect(page.getByPlaceholder(PALETTE_PLACEHOLDER)).toBeHidden({ timeout: 5000 });
    });

    test("palette Getting Started action opens tutorial modal", async ({ page }) => {
        await page.goto("/#/messages");
        await waitForBootReady(page);
        await openCommandPalette(page);
        const input = page.getByPlaceholder(PALETTE_PLACEHOLDER);
        await input.fill("Getting Started");
        await page.keyboard.press("Enter");
        await expect(page.getByRole("heading", { name: /Welcome to\s*Meshchat neXt/i }).first()).toBeVisible({
            timeout: 20000,
        });
    });
});

test.describe("Sidebar and keyboard navigation", () => {
    test("sidebar links navigate across main sections", async ({ page, request }) => {
        test.setTimeout(120000);
        await prepareE2eSession(request);
        await page.goto("/#/messages");
        await waitForBootReady(page);
        await page.evaluate(() => {
            localStorage.setItem("map_onboarding_seen", "true");
        });
        await expect(page).toHaveURL(/#\/messages/);

        const sideNav = page.getByRole("navigation", { name: "Primary", exact: true });

        await sideNav.locator('a[href*="#/nomadnetwork"]').click();
        await expect(page).toHaveURL(/#\/nomadnetwork/);

        await sideNav.locator('a[href*="#/map"]').click();
        await expect(page).toHaveURL(/#\/map/);
        await dismissMapOnboardingTooltip(page);

        await sideNav.locator('a[href*="#/tools"]').click();
        await expect(page).toHaveURL(/#\/tools/);
        await expect(page.getByText("Tools", { exact: true }).first()).toBeVisible({
            timeout: 20000,
        });

        await sideNav.getByRole("link", { name: "Settings", exact: true }).click();
        await expect(page).toHaveURL(/#\/settings/);
        await expect(page.getByText("Profile", { exact: true }).first()).toBeVisible({ timeout: 20000 });

        await page.getByTestId("sidebar-more-toggle").click();
        await sideNav.locator('a[href*="#/about"]').click();
        await expect(page).toHaveURL(/#\/about/);
        await expect(page.getByText("Meshchat neXt", { exact: true }).first()).toBeVisible({ timeout: 20000 });
    });

    test("Alt+1 jumps to Messages from another route", async ({ page, request }) => {
        await prepareE2eSession(request);
        await page.goto("/#/contacts");
        await waitForBootReady(page);
        await expect(page).toHaveURL(/#\/contacts/);
        await page.keyboard.press("Alt+1");
        await expect(page).toHaveURL(/#\/messages/, { timeout: 15000 });
    });

    test("Alt+S opens Settings", async ({ page, request }) => {
        await prepareE2eSession(request);
        await page.goto("/#/map");
        await waitForBootReady(page);
        await page.evaluate(() => {
            localStorage.setItem("map_onboarding_seen", "true");
        });
        await expect(page).toHaveURL(/#\/map/);
        await page.keyboard.press("Alt+s");
        await expect(page).toHaveURL(/#\/settings/, { timeout: 15000 });
    });
});

test.describe("Tools hub", () => {
    test("tools index lists utilities heading", async ({ page }) => {
        await page.goto("/#/tools");
        await waitForBootReady(page);
        await expect(page.locator("div.text-2xl.md\\:text-3xl.font-black").first()).toHaveText("Tools", {
            timeout: 20000,
        });
        await expect(page.getByPlaceholder("Search tools...", { exact: true })).toBeVisible();
    });

    test("deep link to paper message tool", async ({ page }) => {
        await page.goto("/#/tools/paper-message");
        await waitForBootReady(page);
        await expect(page).toHaveURL(/#\/tools\/paper-message/);
        await expect(page.getByRole("heading", { name: "Paper Message", exact: true })).toBeVisible({
            timeout: 20000,
        });
    });
});
