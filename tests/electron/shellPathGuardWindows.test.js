import path from "node:path";
import { describe, expect, it } from "vitest";
import { isPathWithinRoot } from "../../electron/shellPathGuard.js";

// Test the same containment predicate with Windows paths on every host.
describe("Windows shell path containment", () => {
    const home = "E:/synthetic-next-profile";
    const roots = [".meshchat-next", ".reticulum", "downloads/Meshchat neXt"].map((name) =>
        path.win32.join(home, name)
    );
    it.each([
        ["own storage", "E:/synthetic-next-profile/.meshchat-next/file.bin", true],
        ["same-drive sibling", "E:/outside/file.bin", false],
        ["other drive", "C:/outside/file.bin", false],
        ["UNC share", "//synthetic-next-server/share/file.bin", false],
        ["prefix sibling", "E:/synthetic-next-profile/.meshchat-next-other/file.bin", false],
        ["exchange", "E:/synthetic-next-profile/downloads/Meshchat neXt/file.bin", true],
        ["loose download", "E:/synthetic-next-profile/downloads/file.bin", false],
    ])("%s", (_name, target, allowed) => {
        expect(roots.some((root) => isPathWithinRoot(root, target, path.win32))).toBe(allowed);
    });
});
