"use strict";

const { execFileSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const BACKEND_IMAGE_UNIX = "MeshchatNext";

/**
 * @param {string} args
 * @returns {boolean}
 */
function isHeadlessBackendArgs(args) {
    if (typeof args !== "string" || !args) {
        return false;
    }
    if (!args.includes(BACKEND_IMAGE_UNIX)) {
        return false;
    }
    return /\s--headless(?:\s|$)/.test(args) || args.endsWith(" --headless");
}

/**
 * @param {number|null|undefined} ownPid
 * @returns {number[]}
 */
function listUnixBackendPids(ownPid = null, scope = null) {
    // A process name alone does not prove ownership. Never sweep the host
    // without an exact executable and profile, including in unit tests.
    if (process.platform !== "linux" || !scope?.executablePath || !scope?.storageDir || !scope?.reticulumConfigDir) {
        return [];
    }
    try {
        const expectedExe = fs.realpathSync(scope.executablePath);
        const expectedStorage = fs.realpathSync(scope.storageDir);
        const expectedConfig = fs.realpathSync(scope.reticulumConfigDir);
        const out = execFileSync("ps", ["-eo", "pid=,args="], {
            encoding: "utf8",
            maxBuffer: 8 * 1024 * 1024,
        });
        const pids = [];
        for (const line of out.split(/\n/)) {
            const trimmed = line.trim();
            if (!trimmed) {
                continue;
            }
            const match = trimmed.match(/^(\d+)\s+(.*)$/);
            if (!match) {
                continue;
            }
            const pid = Number(match[1]);
            if (!Number.isFinite(pid) || pid <= 0) {
                continue;
            }
            if (ownPid != null && pid === ownPid) {
                continue;
            }
            if (pid === process.pid) {
                continue;
            }
            if (!isHeadlessBackendArgs(match[2])) {
                continue;
            }
            try {
                const procDir = `/proc/${pid}`;
                if (fs.statSync(procDir).uid !== process.getuid()) continue;
                const status = fs.readFileSync(`${procDir}/status`, "utf8");
                // A live Electron shell still owns this process. A unit test
                // or another profile must never stop it.
                if (!/^PPid:\s+1\s*$/m.test(status)) continue;
                if (fs.realpathSync(`${procDir}/exe`) !== expectedExe) continue;
                const argv = fs.readFileSync(`${procDir}/cmdline`, "utf8").split("\0").filter(Boolean);
                if (path.basename(argv[0] || "") !== BACKEND_IMAGE_UNIX || !argv.includes("--headless")) continue;
                function flagValue(flag) {
                    const values = [];
                    for (let i = 1; i < argv.length; i += 1) {
                        if (argv[i] === flag) values.push(argv[i + 1]);
                        else if (argv[i].startsWith(`${flag}=`)) values.push(argv[i].slice(flag.length + 1));
                    }
                    return values.length === 1 && values[0] ? fs.realpathSync(values[0]) : null;
                }
                if (flagValue("--storage-dir") !== expectedStorage) continue;
                if (flagValue("--reticulum-config-dir") !== expectedConfig) continue;
            } catch {
                // An exited process or uncertain ownership is never a reason
                // to send a signal.
                continue;
            }
            pids.push(pid);
        }
        return pids;
    } catch {
        return [];
    }
}

function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * @param {number[]} pids
 * @returns {Promise<void>}
 */
async function killUnixPids(pids, stillOwned = () => true) {
    if (!Array.isArray(pids)) {
        return;
    }
    for (const pid of pids) {
        try {
            if (!stillOwned(pid)) continue;
            process.kill(pid, "SIGTERM");
        } catch {
            /* process may already be gone */
        }
    }
    const deadline = Date.now() + 1500;
    while (Date.now() < deadline) {
        let remaining = 0;
        for (const pid of pids) {
            try {
                if (!stillOwned(pid)) continue;
                process.kill(pid, 0);
                remaining += 1;
            } catch {
                /* gone */
            }
        }
        if (remaining === 0) {
            return;
        }
        // Yield instead of spinning so the main-process loop stays responsive.
        await sleep(50);
    }
    for (const pid of pids) {
        try {
            if (!stillOwned(pid)) continue;
            process.kill(pid, "SIGKILL");
        } catch {
            /* process may already be gone */
        }
    }
}

/**
 * @param {number|null|undefined} ownPid Pid to exclude (own backend or a
 *   maintenance child that must not be reaped).
 * @returns {Promise<number>}
 */
async function killOrphanBackendProcesses(ownPid = null, scope = null) {
    // Other platforms cannot currently prove orphan/profile ownership here.
    // Let the existing storage lock report conflicts instead of killing an
    // unrelated live backend by image name.
    if (process.platform !== "linux") return 0;
    const pids = listUnixBackendPids(ownPid, scope);
    // Recheck ownership immediately before each signal to narrow PID reuse
    // races and avoid signalling a process whose parent/profile changed.
    const owned = pids.filter((pid) => listUnixBackendPids(ownPid, scope).includes(pid));
    await killUnixPids(owned, (pid) => listUnixBackendPids(ownPid, scope).includes(pid));
    return owned.length;
}

module.exports = {
    BACKEND_IMAGE_UNIX,
    isHeadlessBackendArgs,
    killOrphanBackendProcesses,
    killUnixPids,
    listUnixBackendPids,
};
