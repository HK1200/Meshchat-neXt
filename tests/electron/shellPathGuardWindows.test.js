import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { describe, expect, it } from "vitest";

// Exercise real Windows path semantics on every CI host, without network I/O.
function windowsGuard() {
    const code = fs.readFileSync(new URL("../../electron/shellPathGuard.js", import.meta.url), "utf8");
    const module = { exports: {} };
    vm.runInNewContext(code, {
        module,
        process: { env: {}, argv: [] },
        require(name) {
            if (name === "node:path") return path.win32;
            if (name === "fs")
                return {
                    realpathSync() {
                        throw new Error("Synthetic nonexistent path");
                    },
                };
            if (name === "./mainHelpers") return { parseArgvFlag: () => null };
            throw new Error(`Unexpected module: ${name}`);
        },
    });
    return module.exports.isAllowedShellPath;
}

describe("Windows shell path containment", () => {
    const home = "E:/synthetic-next-profile";
    const ctx = {
        app: { getPath: (name) => path.win32.join(home, name) },
        getDefaultStorageDir: () => path.win32.join(home, ".meshchat-next"),
        getDefaultReticulumConfigDir: () => path.win32.join(home, ".reticulum"),
        getUserProvidedArguments: () => [],
    };
    it.each([
        ["own storage", "E:/synthetic-next-profile/.meshchat-next/file.bin", true],
        ["same-drive sibling", "E:/outside/file.bin", false],
        ["other drive", "C:/outside/file.bin", false],
        ["UNC share", "//synthetic-next-server/share/file.bin", false],
        ["prefix sibling", "E:/synthetic-next-profile/.meshchat-next-other/file.bin", false],
        ["exchange", "E:/synthetic-next-profile/downloads/Meshchat neXt/file.bin", true],
        ["loose download", "E:/synthetic-next-profile/downloads/file.bin", false],
    ])("%s", (_name, target, allowed) => {
        expect(windowsGuard()(target, ctx, { broadRoots: false })).toBe(allowed);
    });
});
