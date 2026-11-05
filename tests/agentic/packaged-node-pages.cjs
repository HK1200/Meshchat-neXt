// SPDX-License-Identifier: 0BSD
// Actual packaged Windows renderer + backend. MeshCore responses are synthetic;
// all MeshCore requests are intercepted, so this never operates a radio.
const { chromium, expect } = require("@playwright/test");
const fs = require("node:fs");
const path = require("node:path");
const net = require("node:net");
const crypto = require("node:crypto");
const cp = require("node:child_process");
const root = path.resolve(__dirname, "../..");
const exe = path.join(root, "dist/win-unpacked/Meshchat neXt.exe");
const results = [];
const expectedVersion = JSON.parse(fs.readFileSync(path.join(root, "package.json"), "utf8")).version;
const peer = "b2".repeat(32),
    repeater = "c3".repeat(32),
    owner = "a1".repeat(32);
async function portClosed(port) {
    for (let i = 0; i < 60; i++) {
        const open = await new Promise((resolve) => {
            const socket = net.connect({ host: "127.0.0.1", port });
            socket.setTimeout(500);
            socket.once("connect", () => {
                socket.destroy();
                resolve(true);
            });
            socket.once("error", () => {
                socket.destroy();
                resolve(false);
            });
            socket.once("timeout", () => {
                socket.destroy();
                resolve(true);
            });
        });
        if (!open) return true;
        await new Promise((resolve) => setTimeout(resolve, 500));
    }
    throw new Error("Packaged backend listener remained after Quit");
}
async function freePort() {
    const server = net.createServer();
    await new Promise((resolve, reject) => {
        server.once("error", reject);
        server.listen(0, "127.0.0.1", resolve);
    });
    const port = server.address().port;
    await new Promise((resolve) => server.close(resolve));
    return port;
}
async function connectRenderer(port, process) {
    const deadline = Date.now() + 120000;
    while (Date.now() < deadline) {
        if (process.exitCode !== null) throw Error(`Packaged app exited during startup: ${process.exitCode}`);
        try {
            return await chromium.connectOverCDP(`http://127.0.0.1:${port}`, { timeout: 2000 });
        } catch {
            await new Promise((resolve) => setTimeout(resolve, 500));
        }
    }
    throw Error("Packaged renderer did not expose the loopback-only CI connection within startup timeout");
}
async function verifyFuses() {
    const { getCurrentFuseWire, FuseV1Options, FuseState } = await import("@electron/fuses");
    const wire = await getCurrentFuseWire(exe);
    for (const option of [
        FuseV1Options.RunAsNode,
        FuseV1Options.EnableNodeOptionsEnvironmentVariable,
        FuseV1Options.EnableNodeCliInspectArguments,
    ])
        if (wire[option] !== FuseState.DISABLE) throw Error("Packaged Electron execution fuse was weakened");
    for (const option of [FuseV1Options.EnableEmbeddedAsarIntegrityValidation, FuseV1Options.OnlyLoadAppFromAsar])
        if (wire[option] !== FuseState.ENABLE) throw Error("Packaged ASAR integrity fuse was weakened");
}
async function run(mode) {
    const base = fs.mkdtempSync(path.join(root, "temp-tests", "windows-node-ui-"));
    const storage = path.join(base, "storage"),
        rns = path.join(base, "reticulum");
    fs.mkdirSync(storage);
    fs.mkdirSync(rns);
    fs.writeFileSync(
        path.join(rns, "config"),
        "[reticulum]\n  enable_transport = No\n  share_instance = No\n[interfaces]\n"
    );
    const sentinel = crypto.randomBytes(32);
    fs.writeFileSync(path.join(storage, "profile-sentinel"), sentinel);
    fs.writeFileSync(
        path.join(storage, "desktop-close-settings.json"),
        JSON.stringify({ closeBehavior: "quit", trayEnabled: false })
    );
    const env = { ...process.env, MESHCHAT_FORCE_STDOUT_LOG: "1" };
    delete env.MESHCHAT_APPCONTAINER;
    if (mode === "forced") env.MESHCHAT_APPCONTAINER = "1";
    let appProcess, browser;
    let diagnostic = "";
    const debugPort = await freePort();
    try {
        // Keep hardened Node-inspector fuses disabled. Only the renderer CDP
        // endpoint is enabled, on loopback in this disposable CI fixture.
        appProcess = cp.spawn(
            exe,
            [
                `--storage-dir=${storage}`,
                `--reticulum-config-dir=${rns}`,
                `--remote-debugging-port=${debugPort}`,
                "--remote-debugging-address=127.0.0.1",
                "--enable-automation",
            ],
            { env, stdio: ["ignore", "pipe", "pipe"] }
        );
        for (const stream of [appProcess.stdout, appProcess.stderr])
            stream.on("data", (chunk) => {
                diagnostic = (diagnostic + chunk.toString()).slice(-64000);
            });
        appProcess.on("error", (error) => console.error("Packaged launch error", error.message));
        browser = await connectRenderer(debugPort, appProcess);
        const context = browser.contexts()[0];
        context.setDefaultTimeout(30000);
        await context.addInitScript(() => {
            localStorage.setItem(
                "meshchatnext.post_install_prompts_seen",
                JSON.stringify({ windows_screen_security: 1 })
            );
        });
        await context.route("**/api/v1/meshcore/**", async (route) => {
            if (new URL(route.request().url()).pathname.endsWith("/ui")) {
                await route.fulfill({
                    json: {
                        result: {
                            owner,
                            radio_id: "synthetic",
                            connected: true,
                            available: true,
                            contacts: [{ peer: "abcd1234" + "11".repeat(28), name: "Alice", active: true }],
                            nodes: [
                                { peer, kind: 3, name: "Fixture room" },
                                { peer: repeater, kind: 2, name: "Fixture repeater" },
                            ],
                            announces: [],
                            channels: [],
                            links: [],
                            conversations: [],
                            node_sessions: {
                                [peer]: { state: "verified", is_admin: true },
                                [repeater]: { state: "verified", is_admin: true },
                            },
                            node_operations: {},
                            messages: [
                                {
                                    id: "fixture-post",
                                    peer,
                                    direction: "in",
                                    text: "Synthetic room post",
                                    created: Math.floor(Date.now() / 1000),
                                    payload: JSON.stringify({ event: { txt_type: 2, signature: "abcd1234" } }),
                                },
                            ],
                        },
                    },
                });
            } else await route.fulfill({ json: { result: [], status: { available: false } } });
        });
        const page = context.pages()[0] || (await context.waitForEvent("page", { timeout: 30000 }));
        await page.waitForURL(/^https?:\/\//, { timeout: 120000 });
        await page.waitForFunction(() => Boolean(window.api), {}, { timeout: 120000 });
        const backendVersion = await page.evaluate(async (version) => {
            const info = (await window.api.get("/api/v1/app/info")).data.app_info;
            await window.api.post("/api/v1/app/tutorial/seen", {});
            await window.api.post("/api/v1/app/changelog/seen", { version });
            return info.version;
        }, expectedVersion);
        if (backendVersion !== expectedVersion) throw Error("Unexpected packaged backend version");
        // Fixture preparation uses the real app API and its normal loopback TLS
        // handling. Reload into that saved fixture state; not onboarding coverage.
        await page.reload();
        await page.waitForFunction(() => Boolean(window.api), {}, { timeout: 120000 });
        const security = await page.evaluate(async () => (await window.api.get("/api/v1/server/security")).data);
        if (mode === "forced" && !security.appcontainer_active) throw Error("Forced AppContainer was not active");
        const version = await page.evaluate(async () => window.electron.appVersion());
        if (version !== expectedVersion) throw Error("Unexpected packaged frontend version");
        const renderer = await page.evaluate(() => ({
            nodeGlobalsAbsent: typeof require === "undefined" && typeof process === "undefined",
            trustedPreloadBridge: typeof window.electron?.appVersion === "function",
        }));
        if (!renderer.nodeGlobalsAbsent || !renderer.trustedPreloadBridge)
            throw Error("Packaged renderer isolation was weakened");
        const browserSession = await browser.newBrowserCDPSession();
        const commandLine = await browserSession.send("Browser.getBrowserCommandLine");
        if (
            commandLine.arguments.some(
                (argument) => argument === "--no-sandbox" || argument === "--disable-gpu-sandbox"
            )
        )
            throw Error("Packaged Chromium sandbox was disabled");
        const origin = new URL(page.url()).origin,
            port = Number(new URL(page.url()).port);
        await page.goto(`${origin}/#/meshcore/nodes/${peer}`);
        await expect(page.getByRole("heading", { name: "Fixture room", exact: true })).toBeVisible();
        await expect(page.getByLabel("Room conversation", { exact: true })).toBeVisible();
        await expect(page.locator("article").filter({ hasText: "Synthetic room post" })).toContainText("Alice");
        await page.locator("textarea").fill("Retain this synthetic draft");
        await page.getByRole("button", { name: "Access", exact: true }).click();
        await expect(page.getByLabel("Node access", { exact: true })).toBeVisible();
        await page.getByRole("button", { name: "Manage", exact: true }).click();
        await page.getByText("Radio & routing", { exact: true }).click();
        await page.getByRole("button", { name: "Change radio profile", exact: true }).click();
        await expect(page.getByRole("button", { name: "Run server action", exact: true })).toBeDisabled();
        await page.getByRole("button", { name: "Messages", exact: true }).click();
        await expect(page.locator("textarea")).toHaveValue("Retain this synthetic draft");
        await page.goto(`${origin}/#/meshcore/nodes/${repeater}`);
        await expect(page.getByRole("button", { name: "Overview", exact: true })).toHaveAttribute(
            "aria-pressed",
            "true"
        );
        await expect(page.getByLabel("Node status", { exact: true })).toBeVisible();
        await page.evaluate(async () =>
            window.electron.setCloseSettings({ closeBehavior: "quit", trayEnabled: false })
        );
        const closing = new Promise((resolve, reject) => {
            const timer = setTimeout(() => reject(Error("Packaged app did not exit after normal Quit")), 30000);
            appProcess.once("exit", (code) => {
                clearTimeout(timer);
                if (code !== 0) reject(Error(`Packaged app exited abnormally: ${code}`));
                else resolve();
            });
        });
        await page
            .evaluate(() => window.close())
            .catch((error) => {
                if (!/closed/i.test(error.message)) throw error;
            });
        await closing;
        await portClosed(port);
        await portClosed(debugPort);
        if (!fs.readFileSync(path.join(storage, "profile-sentinel")).equals(sentinel))
            throw Error("Profile sentinel changed");
        results.push({
            mode,
            packaged_version: version,
            appcontainer_active: Boolean(security.appcontainer_active),
            actual_packaged_ui: true,
            normal_chromium_commandline: true,
            hardened_execution_and_asar_fuses: true,
            renderer_node_globals_absent: true,
            trusted_preload_bridge: true,
            synthetic_meshcore_only: true,
            task_tabs: true,
            room_contact_name: true,
            draft_preserved: true,
            disruptive_action_guard: true,
            repeater_default: true,
            normal_quit: true,
            backend_listener_closed: true,
            profile_preserved: true,
        });
        console.log(JSON.stringify(results.at(-1)));
    } catch (error) {
        console.error("Synthetic packaged fixture diagnostics:", diagnostic);
        if (browser) {
            for (const page of browser.contexts()[0].pages()) {
                console.error("Synthetic renderer URL:", page.url());
                console.error(
                    "Synthetic startup state:",
                    await page
                        .evaluate(async () => {
                            const info = await window.electron?.backendStartupDiagnostics?.();
                            return {
                                runtime: info?.runtime,
                                exitCode: info?.crash?.code,
                                stderr: info?.crash?.stderr?.slice(-6000),
                            };
                        })
                        .catch(() => "Trusted startup diagnostics unavailable")
                );
            }
        }
        throw error;
    } finally {
        if (browser) await browser.close();
        if (appProcess && appProcess.exitCode === null) {
            console.error("Failure cleanup: terminating only the owned synthetic fixture process");
            appProcess.kill();
        }
        fs.rmSync(base, { recursive: true, force: true });
    }
}
(async () => {
    if (process.platform !== "win32")
        throw Error("This native package check must run on Windows; Linux is not equivalent evidence");
    if (!fs.existsSync(exe)) throw Error(`Missing packaged executable: ${exe}`);
    await verifyFuses();
    fs.mkdirSync(path.join(root, "temp-tests"), { recursive: true });
    for (const mode of ["default", "forced"]) await run(mode);
    fs.mkdirSync(path.join(root, "reports"), { recursive: true });
    fs.writeFileSync(
        path.join(root, "reports/windows-node-ui.json"),
        JSON.stringify(
            {
                source: cp.execFileSync("git", ["rev-parse", "HEAD"], { cwd: root, encoding: "utf8" }).trim(),
                passed: true,
                results,
            },
            null,
            2
        )
    );
})().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
