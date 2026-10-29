#!/usr/bin/env node
// SPDX-License-Identifier: 0BSD

import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { spawnSync } from "child_process";
import { createRequire } from "module";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, "..");
const SRC_CSS = path.join(REPO_ROOT, "electron", "assets", "css", "electron-shell.src.css");
const ELECTRON_OUT = path.join(REPO_ROOT, "electron", "assets", "css", "electron-shell.css");
const PUBLIC_OUT = path.join(
    REPO_ROOT,
    "meshchatnext",
    "src",
    "frontend",
    "public",
    "assets",
    "css",
    "electron-shell.css"
);

function ensureParentDir(filePath) {
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
}

function buildCss() {
    // Invoke the installed JS CLI directly: Windows cannot exec pnpm.cmd
    // without a shell, and paths must remain individual arguments.
    const require = createRequire(import.meta.url);
    const packagePath = require.resolve("@tailwindcss/cli/package.json");
    const metadata = JSON.parse(fs.readFileSync(packagePath, "utf8"));
    const cliPath = path.resolve(path.dirname(packagePath), metadata.bin.tailwindcss);
    const result = spawnSync(process.execPath, [cliPath, "-i", SRC_CSS, "-o", ELECTRON_OUT, "--minify"], {
        cwd: REPO_ROOT,
        stdio: "inherit",
    });
    if (result.error) {
        console.error(`build-electron-shell-css: ${result.error.message}`);
    }
    if (result.status !== 0) {
        process.exit(result.status ?? 1);
    }
}

function copyToPublic() {
    ensureParentDir(PUBLIC_OUT);
    fs.copyFileSync(ELECTRON_OUT, PUBLIC_OUT);
}

if (process.env.MESHCHATNEXT_SKIP_ELECTRON_CSS === "1") {
    console.log("build-electron-shell-css: skipped (MESHCHATNEXT_SKIP_ELECTRON_CSS=1)");
    process.exit(0);
}

if (!fs.existsSync(SRC_CSS)) {
    console.error(`build-electron-shell-css: missing source ${SRC_CSS}`);
    process.exit(1);
}

buildCss();
copyToPublic();
console.log(`Wrote ${ELECTRON_OUT}`);
console.log(`Copied to ${PUBLIC_OUT}`);
