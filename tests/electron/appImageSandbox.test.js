import { expect, it } from "vitest";
import { createRequire } from "node:module";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFileSync } from "node:child_process";
const require = createRequire(import.meta.url);
const bash =
    process.platform === "win32"
        ? path.join(process.env.ProgramFiles || "C:/Program Files", "Git", "bin", "bash.exe")
        : "bash";
const { patch } = require("../../scripts/patch-electron-appimage-sandbox.cjs");
it("patches the known template idempotently and rejects unknown templates", () => {
    const source =
        "before\nHAVE_NO_SANDBOX=0\nif ! unshare -Ur true; then NO_SANDBOX=(--no-sandbox); fi\natexit()\nafter";
    const result = patch(source);
    expect(result).not.toContain("--no-sandbox");
    expect(patch(result)).toBe(result);
    expect(() => patch("unknown version")).toThrow("review sandbox policy");
});
it(
    "the actual generated launcher keeps sandboxing when unshare fails",
    () => {
        execFileSync(process.execPath, [path.resolve("scripts/patch-electron-appimage-sandbox.cjs")], {
            encoding: "utf8",
        });
        const { generateAppRunScript } = require("app-builder-lib/out/targets/appimage/appImageUtil.js");
        const root = fs.mkdtempSync(path.join(process.env.TMPDIR || os.tmpdir(), "next-apprun-test-"));
        try {
            const file = path.join(root, "AppRun");
            fs.writeFileSync(
                file,
                generateAppRunScript({
                    ExecutableName: "meshchat-next",
                    ProductName: "Meshchat neXt",
                    ProductFilename: "Meshchat neXt",
                }),
                { mode: 0o755 }
            );
            fs.writeFileSync(path.join(root, "unshare"), "#!/bin/sh\nexit 1\n", { mode: 0o755 });
            fs.writeFileSync(
                path.join(root, "meshchat-next"),
                '#!/bin/sh\nprintf \'%s\\n\' "$@" > "$APPDIR/received-args"\n',
                { mode: 0o755 }
            );
            const shellRoot =
                process.platform === "win32"
                    ? execFileSync(bash, ["-c", 'cygpath -u "$1"', "_", root], { encoding: "utf8" }).trim()
                    : root;
            const shellFile = `${shellRoot}/AppRun`;
            execFileSync(bash, [shellFile, "--headless"], {
                env: {
                    ...process.env,
                    APPDIR: shellRoot,
                    PATH: process.platform === "win32" ? `${shellRoot}:/usr/bin:/bin` : `${root}:${process.env.PATH}`,
                },
                encoding: "utf8",
            });
            const args = fs.readFileSync(path.join(root, "received-args"), "utf8");
            expect(args).toContain("--headless");
            expect(args).not.toContain("--no-sandbox");
        } finally {
            fs.rmSync(root, { recursive: true, force: true });
        }
    },
    process.platform === "win32" ? 15000 : 5000
);
