import { describe, expect, it } from "vitest";
import fs from "node:fs";
import vm from "node:vm";
import path from "node:path";
import { fileURLToPath } from "node:url";

// Execute the real module against an entirely synthetic process table. No
// test may enumerate or signal host processes, even when run outside a sandbox.
const source = fs.readFileSync(fileURLToPath(new URL("../../electron/backendProcessOrphans.js", import.meta.url)), "utf8");
const scope = { executablePath: "/app/MeshchatNext", storageDir: "/profile one", reticulumConfigDir: "/config one" };

function fixture(overrides = {}, platform = "linux") {
    const rows = new Map(Object.entries({
        101: { parent: 700, uid: 1000 }, // The owner's live desktop backend.
        102: { parent: 1, uid: 1000 }, // An actual matching orphan.
        103: { parent: 1, uid: 1001 }, // Another user.
        104: { parent: 1, uid: 1000, storage: "/other profile" },
        105: { parent: 1, uid: 1000, exe: "/other/MeshchatNext" },
        106: { parent: 1, uid: 1000, config: "/other config" },
        107: { parent: 1, uid: 1000, argv0: "/bin/echo" },
        108: { parent: 1, uid: 1000, malformed: true },
        ...overrides,
    }).filter(([, row]) => row !== null).map(([pid, row]) => [Number(pid), row]));
    const signals = [];
    let enumerations = 0;
    const get = (p) => {
        const pid = Number(/^\/proc\/(\d+)/.exec(p)?.[1]);
        if (!rows.has(pid)) throw new Error("process gone");
        return rows.get(pid);
    };
    const fakeFs = {
        realpathSync(p) {
            if (p.startsWith("/proc/")) return get(p).exe || scope.executablePath;
            return p;
        },
        statSync(p) { return { uid: get(p).uid }; },
        readFileSync(p) {
            const row = get(p);
            if (row.malformed) throw new Error("cannot prove ownership");
            if (p.endsWith("/status")) return `Name:\tMeshchatNext\nPPid:\t${row.parent}\n`;
            const args = [row.argv0 || scope.executablePath, "--headless", "--storage-dir", row.storage || scope.storageDir, `--reticulum-config-dir=${row.config || scope.reticulumConfigDir}`];
            if (row.duplicate) args.push("--storage-dir=/other profile");
            return args.join("\0") + "\0";
        },
    };
    const fakeProcess = {
        platform, pid: 9999, getuid: () => 1000,
        kill(pid, signal) {
            signals.push([pid, signal]);
            if (!rows.has(pid)) throw new Error("process gone");
            if (signal === "SIGTERM") rows.delete(pid);
        },
    };
    const module = { exports: {} };
    vm.runInNewContext(source, {
        module, process: fakeProcess, Date, setTimeout,
        require(name) {
            if (name === "node:fs") return fakeFs;
            if (name === "node:path") return path;
            if (name === "node:child_process") return { execFileSync() {
                enumerations += 1;
                return [...rows.keys()].map((pid) => `${pid} /app/MeshchatNext --headless`).join("\n");
            } };
            throw new Error(`Unexpected host dependency: ${name}`);
        },
    }, { timeout: 1000 });
    return { api: module.exports, rows, signals, process: fakeProcess, enumerations: () => enumerations };
}

describe("electron/backendProcessOrphans host safety", () => {
    it("detects headless backend command lines", () => {
        const { api } = fixture();
        expect(api.isHeadlessBackendArgs("/tmp/.mount_x/resources/backend/MeshchatNext --headless --port 9338")).toBe(true);
        expect(api.isHeadlessBackendArgs("/home/user/MeshchatNext --headless")).toBe(true);
    });
    it("ignores non-backend and non-headless processes", () => {
        const { api } = fixture();
        expect(api.isHeadlessBackendArgs("meshchat-next --type=renderer")).toBe(false);
        expect(api.isHeadlessBackendArgs("/tmp/MeshchatNext")).toBe(false);
        expect(api.isHeadlessBackendArgs("")).toBe(false);
        expect(api.isHeadlessBackendArgs(null)).toBe(false);
    });
    it("killOrphanBackendProcesses is async and resolves with a count", async () => {
        const f = fixture();
        const result = f.api.killOrphanBackendProcesses(9999);
        expect(typeof result.then).toBe("function");
        expect(typeof (await result)).toBe("number");
    });
    it("killUnixPids reaps a synthetic process without blocking the event loop", async () => {
        const f = fixture();
        const originalKill = f.process.kill;
        f.process.kill = (pid, signal) => {
            if (signal === "SIGTERM") {
                f.signals.push([pid, signal]);
                setTimeout(() => f.rows.delete(pid), 30);
                return;
            }
            return originalKill(pid, signal);
        };
        const intervalTicks = [];
        const interval = setInterval(() => intervalTicks.push(Date.now()), 10);
        try {
            await f.api.killUnixPids([102]);
        } finally {
            clearInterval(interval);
        }
        // Preserve the original responsiveness and reaping assertions without
        // spawning or signalling any host process.
        expect(intervalTicks.length).toBeGreaterThan(0);
        expect(() => f.process.kill(102, 0)).toThrow();
    });
    it("does not enumerate or signal the host without an explicit ownership scope", async () => {
        const f = fixture();
        expect(await f.api.killOrphanBackendProcesses(9999)).toBe(0);
        expect(f.enumerations()).toBe(0);
        expect(f.signals).toEqual([]);
    });
    it("selects only a same-user, same-executable, same-profile orphan", () => {
        const f = fixture();
        expect(Array.from(f.api.listUnixBackendPids(null, scope))).toEqual([102]);
    });
    it("never signals the owner's backend while its Electron parent is alive", async () => {
        const f = fixture();
        expect(await f.api.killOrphanBackendProcesses(null, scope)).toBe(1);
        expect(f.signals).toEqual([[102, "SIGTERM"]]);
        expect(f.rows.has(101)).toBe(true);
    });
    it("excludes the caller's maintenance process", async () => {
        const f = fixture();
        expect(await f.api.killOrphanBackendProcesses(102, scope)).toBe(0);
        expect(f.signals).toEqual([]);
    });
    it("rejects duplicate profile arguments", () => {
        const f = fixture({ 102: { parent: 1, uid: 1000, duplicate: true } });
        expect(Array.from(f.api.listUnixBackendPids(null, scope))).toEqual([]);
    });
    it("fails closed on platforms without validated ownership inspection", async () => {
        for (const platform of ["darwin", "win32"]) {
            const f = fixture({}, platform);
            expect(await f.api.killOrphanBackendProcesses(null, scope)).toBe(0);
            expect(f.enumerations()).toBe(0);
            expect(f.signals).toEqual([]);
        }
    });
    it("does not signal a PID whose ownership changes during revalidation", async () => {
        const f = fixture();
        let count = 0;
        const original = f.rows.get(102);
        Object.defineProperty(original, "parent", { get() { return ++count === 1 ? 1 : 700; } });
        expect(await f.api.killOrphanBackendProcesses(null, scope)).toBe(0);
        expect(f.signals).toEqual([]);
    });
});
