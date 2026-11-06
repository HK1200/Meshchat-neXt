// SPDX-License-Identifier: 0BSD
// electron-builder omits directory markers despite the explicit filter.
// Restore only the byte-identical signed-source marker before packaging EXEs.
const fs = require("node:fs");
const crypto = require("node:crypto");
const path = require("node:path");
module.exports = async context => {
    const base = path.join(process.env.MESHCHAT_RELEASE_REVIEW_ROOT, "source/build/exe/win32-x64");
    const relative = "lib/meshchatnext/src/backend/data/map/.gitkeep";
    const source = path.join(base, relative);
    const destination = path.join(context.appOutDir, "resources/backend", relative);
    const bytes = fs.readFileSync(source);
    if (bytes.length !== 115 || crypto.createHash("sha256").update(bytes).digest("hex") !== "7cb201d097d6d9feeb849a1c5289054533e44fe90ffb87c015625ca789e0675c") throw new Error("Signed source marker hash mismatch");
    fs.mkdirSync(path.dirname(destination), { recursive: true });
    fs.copyFileSync(source, destination);
    if (!fs.readFileSync(source).equals(fs.readFileSync(destination))) throw new Error("Marker copy mismatch");
};
