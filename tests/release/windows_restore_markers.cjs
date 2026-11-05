// SPDX-License-Identifier: 0BSD
// electron-builder omits empty directory markers despite the explicit filter.
// Restore only the byte-identical signed-source marker before packaging EXEs.
const fs = require("node:fs");
const path = require("node:path");
module.exports = async context => {
    const base = path.join(process.env.MESHCHAT_RELEASE_REVIEW_ROOT, "source/build/exe/win32-x64");
    const relative = "lib/meshchatnext/src/backend/data/map/.gitkeep";
    const source = path.join(base, relative);
    const destination = path.join(context.appOutDir, "resources/backend", relative);
    if (fs.statSync(source).size !== 0) throw new Error("Expected empty source marker");
    fs.mkdirSync(path.dirname(destination), { recursive: true });
    fs.copyFileSync(source, destination);
    if (!fs.readFileSync(source).equals(fs.readFileSync(destination))) throw new Error("Marker copy mismatch");
};
