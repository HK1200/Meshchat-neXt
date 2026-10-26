/**
 * Single source of truth: set "version" in package.json, then run:
 *   pnpm run version:sync
 *
 * Writes: meshchatnext/__init__.py (__version__), meshchatnext/src/version.py, pyproject.toml [project].version,
 * meshchatnext/src/backend/data/THIRD_PARTY_NOTICES.txt (meshchat-next line only),
 * meshchatnext/src/backend/data/licenses_backend.json (meshchat-next entry),
 * android/app/build.gradle,
 * electron/app-version.json,
 * packaging/arch/PKGBUILD pkgver / printf fallback,
 * then runs scripts/bake_build_meta.js (git commit / channel overlay).
 *
 * Docs and issue templates do not carry the version. Changelog entries stay handwritten.
 *
 * __version__ lives in meshchatnext/__init__.py so Chaquopy/Android (which may not ship loose .py
 * data files next to bytecode) always has a resolvable version. src/version.py stays for packaging and tools.
 * The build script runs version:sync automatically.
 */

const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const pkgPath = path.join(root, "package.json");
const pkg = JSON.parse(fs.readFileSync(pkgPath, "utf8"));
const version = pkg.version;
const release = JSON.parse(fs.readFileSync(path.join(root, "next-release.json"), "utf8"));
const androidDisplayVersion = release.displayVersion;
const androidVersionCode = release.androidVersionCode;

if (!version || typeof version !== "string") {
    console.error("package.json has no valid 'version' field");
    process.exit(1);
}

function writeIfChanged(absPath, content) {
    const prev = fs.existsSync(absPath) ? fs.readFileSync(absPath, "utf8") : null;
    if (prev !== content) {
        fs.writeFileSync(absPath, content, "utf8");
        console.log(`Updated ${path.relative(root, absPath)}`);
    }
}

const versionPy = `"""Version string synced from package.json.

Do not edit by hand. Run: pnpm run version:sync
"""

__version__ = "${version}"
`;
writeIfChanged(path.join(root, "meshchatnext", "src", "version.py"), versionPy);

patchFile("meshchatnext/__init__.py", (c) =>
    c.replace(/^__version__\s*=\s*"[^"]*"\s*$/m, `__version__ = "${version}"`)
);

const pyprojectPath = path.join(root, "pyproject.toml");
let pyproject = fs.readFileSync(pyprojectPath, "utf8");
const pyprojectNext = pyproject.replace(/^version = "[^"]+"/m, `version = "${version}"`);
if (pyprojectNext !== pyproject) {
    fs.writeFileSync(pyprojectPath, pyprojectNext, "utf8");
    console.log(`Updated ${path.relative(root, pyprojectPath)}`);
}

const noticesPath = path.join(root, "meshchatnext", "src", "backend", "data", "THIRD_PARTY_NOTICES.txt");
if (fs.existsSync(noticesPath)) {
    let notices = fs.readFileSync(noticesPath, "utf8");
    const noticesNext = notices.replace(/^meshchat-next .+$/m, `meshchat-next ${version}`);
    if (noticesNext !== notices) {
        fs.writeFileSync(noticesPath, noticesNext, "utf8");
        console.log(`Updated ${path.relative(root, noticesPath)}`);
    }
}

function patchFile(rel, fn) {
    const abs = path.join(root, rel);
    if (!fs.existsSync(abs)) {
        return;
    }
    const before = fs.readFileSync(abs, "utf8");
    const after = fn(before);
    if (after !== before) {
        fs.writeFileSync(abs, after, "utf8");
        console.log(`Updated ${rel}`);
    }
}

const licensesBackendPath = path.join(root, "meshchatnext", "src", "backend", "data", "licenses_backend.json");
if (fs.existsSync(licensesBackendPath)) {
    const licensesBackend = JSON.parse(fs.readFileSync(licensesBackendPath, "utf8"));
    const meshchatEntry = licensesBackend.find((entry) => entry.name === "meshchat-next");
    if (meshchatEntry && meshchatEntry.version !== version) {
        meshchatEntry.version = version;
        fs.writeFileSync(licensesBackendPath, `${JSON.stringify(licensesBackend, null, 4)}\n`, "utf8");
        console.log(`Updated ${path.relative(root, licensesBackendPath)}`);
    }
}

patchFile("android/app/build.gradle", (c) => {
    let x = c.replace(/versionCode \d+/, `versionCode ${androidVersionCode}`);
    x = x.replace(/versionName "[^"]+"/, `versionName "${androidDisplayVersion}"`);
    return x;
});

const archVersion = version.replace(/\+/g, "_").replace(/-/g, "_");

patchFile("packaging/arch/PKGBUILD", (c) => {
    let x = c.replace(/^pkgver=[^\s]+/m, `pkgver=${archVersion}`);
    x = x.replace(/printf "[^"]+\.r%s\.%s"/, `printf "${archVersion}.r%s.%s"`);
    return x;
});

patchFile("packaging/arch/.SRCINFO", (c) =>
    c.replace(/^(\tpkgver = )[^\s]+/m, (_, prefix) => `${prefix}${archVersion}`)
);

patchFile("helm/meshchatnext/Chart.yaml", (c) => c.replace(/^appVersion: "[^"]+"/m, `appVersion: "${version}"`));

console.log(`Synced version ${version} from package.json`);

const appVersionPath = path.join(root, "electron", "app-version.json");
writeIfChanged(appVersionPath, `${JSON.stringify({ version }, null, 4)}\n`);

try {
    require("./bake_build_meta.js");
} catch (err) {
    console.warn(`bake_build_meta skipped: ${err && err.message ? err.message : err}`);
}
