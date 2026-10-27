#!/usr/bin/env node
// SPDX-License-Identifier: 0BSD
const fs = require("node:fs");
const path = require("node:path");
function patch(source) {
    if (source.includes("Meshchat neXt: preserve Chromium sandbox")) return source;
    const start = source.indexOf("HAVE_NO_SANDBOX=0");
    const end = source.indexOf("\natexit()", start);
    if (start < 0 || end < 0 || !source.slice(start, end).includes("unshare -Ur"))
        throw new Error("AppImage launcher template changed; review sandbox policy before packaging");
    return source.slice(0, start) + "# Meshchat neXt: preserve Chromium sandbox; never infer a bypass from unshare.\nNO_SANDBOX=()\n" + source.slice(end);
}
function main() {
    const target = path.resolve(__dirname, "../node_modules/app-builder-lib/out/targets/appimage/appImageUtil.js");
    const original = fs.readFileSync(target, "utf8");
    const updated = patch(original);
    if (updated !== original) fs.writeFileSync(target, updated);
    console.log("AppImage launcher preserves the Chromium sandbox.");
}
if (require.main === module) main();
module.exports = { patch };
