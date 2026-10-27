import { describe, expect, it } from "vitest";
import { createRequire } from "module";

const require = createRequire(import.meta.url);
const { buildRelaunchOptions } = require("../../electron/relaunchOptions.js");

describe("desktop relaunch arguments", () => {
    const argv = [
        "/tmp/extracted/meshchat-next",
        "--remote-debugging-port=18547",
        "--data-dir",
        "/media/fixture with spaces",
        "--no-https",
    ];

    it("keeps custom profile and protocol options when restarting an AppImage", () => {
        const result = buildRelaunchOptions([], {
            argv,
            platform: "linux",
            defaultApp: false,
            env: { APPIMAGE: "/media/Meshchat neXt.AppImage" },
        });
        expect(result).toEqual({
            args: argv.slice(1),
            execPath: "/media/Meshchat neXt.AppImage",
        });
    });

    it("appends recovery flags without changing the original arguments", () => {
        const before = [...argv];
        const result = buildRelaunchOptions(["--emergency"], {
            argv,
            platform: "linux",
            defaultApp: false,
            env: { APPIMAGE: "/media/next.AppImage" },
        });
        expect(result.args).toEqual([...argv.slice(1), "--emergency"]);
        expect(argv).toEqual(before);
    });

    it.each([
        ["linux", false],
        ["win32", false],
        ["linux", true],
    ])("preserves arguments without an AppImage override on %s, defaultApp=%s", (platform, defaultApp) => {
        const result = buildRelaunchOptions([], {
            argv,
            platform,
            defaultApp,
            env: defaultApp ? { APPIMAGE: "/media/dev.AppImage" } : {},
        });
        expect(result).toEqual({ args: argv.slice(1) });
    });
});
