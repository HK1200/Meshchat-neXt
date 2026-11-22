// SPDX-License-Identifier: 0BSD
const { test, expect } = require("@playwright/test");
const { E2E_BACKEND_ORIGIN, prepareE2eSession, e2ePost } = require("../e2e/helpers");
const { waitForBootReady } = require("./ready");

test.describe("Recipient alerts on the real settings page", () => {
    for (const viewport of [
        { name: "desktop", width: 1280, height: 960 },
        { name: "phone", width: 390, height: 844 },
    ]) {
        test(viewport.name, async ({ page, request, baseURL }, testInfo) => {
            await prepareE2eSession(request);
            const infoResponse = await request.get(`${E2E_BACKEND_ORIGIN}/api/v1/app/info`);
            const info = (await infoResponse.json()).app_info || {};
            const key = `${String(info.build_channel || "").toLowerCase()}:${String(info.display_version || info.version || "unknown").trim() || "unknown"}:${String(info.git_commit_short || "").trim() || (info.git_commit ? String(info.git_commit).slice(0, 7) : "") || "unknown"}`;
            await e2ePost(request, `${E2E_BACKEND_ORIGIN}/api/v1/app/channel-prompt/seen`, { key });
            const contactName = `Private mailbox test ${viewport.name}`;
            const address = (viewport.name === "phone" ? "a1" : "a2").repeat(16);
            const added = await e2ePost(request, `${E2E_BACKEND_ORIGIN}/api/v1/telephone/contacts`, {
                name: contactName,
                remote_identity_hash: address,
                lxmf_address: address,
            });
            expect(added.ok()).toBeTruthy();
            const contacts = (await (await request.get(`${E2E_BACKEND_ORIGIN}/api/v1/telephone/contacts`)).json())
                .contacts;
            const contact = contacts.find((row) => row.name === contactName);
            expect(contact).toBeTruthy();
            let providerRequests = 0;
            await page.route("https://alerts.example.invalid/**", (route) => {
                ++providerRequests;
                return route.abort();
            });
            await page.setViewportSize({ width: viewport.width, height: viewport.height });
            await page.goto(`${baseURL}/#/settings?section=family`, { waitUntil: "domcontentloaded" });
            await waitForBootReady(page);
            const details = page
                .locator("details")
                .filter({ has: page.getByText("Optional recipient alerts", { exact: true }) });
            await details.locator("summary").click();
            await details.getByTestId("mailbox-contact").selectOption(String(contact.id));
            await expect(details.getByTestId("mailbox-provider")).toBeEnabled();
            await details.getByTestId("mailbox-provider").fill("https://alerts.example.invalid");
            await details.getByTestId("mailbox-audience").fill("private UI test");
            await details.getByTestId("mailbox-relay").fill("b2".repeat(16));
            await expect(details.getByTestId("mailbox-save")).toBeEnabled();
            await details.getByTestId("mailbox-save").click();
            await expect(details.getByRole("status")).toHaveText("Recipient alert details saved.");
            const saved = await request.get(
                `${E2E_BACKEND_ORIGIN}/api/v1/telephone/contacts/${contact.id}/mailbox-alert-route`
            );
            expect((await saved.json()).route.audience).toBe("private UI test");
            const bounds = await details.boundingBox();
            expect(bounds.x).toBeGreaterThanOrEqual(0);
            expect(bounds.width).toBeLessThanOrEqual(viewport.width);
            await details.screenshot({ path: testInfo.outputPath(`recipient-alerts-${viewport.name}.png`) });
            await details.getByTestId("mailbox-remove").click();
            await expect(details.getByRole("status")).toHaveText("Recipient alerts removed.");
            expect(
                (
                    await (
                        await request.get(
                            `${E2E_BACKEND_ORIGIN}/api/v1/telephone/contacts/${contact.id}/mailbox-alert-route`
                        )
                    ).json()
                ).route
            ).toBeNull();
            expect(providerRequests).toBe(0);
            const remaining = (await (await request.get(`${E2E_BACKEND_ORIGIN}/api/v1/telephone/contacts`)).json())
                .contacts;
            expect(remaining.some((row) => row.id === contact.id)).toBe(true);
        });
    }
});
