/**
 * Keep portable data paths and other launch options through every restart.
 * Supplying execPath for an AppImage does not preserve Electron's arguments
 * reliably, so provide them explicitly even when no extra flags are added.
 */
function buildRelaunchOptions(extraArgs = [], runtime = process) {
    const options = { args: runtime.argv.slice(1).concat(extraArgs) };
    if (!runtime.defaultApp && runtime.platform === "linux" && runtime.env.APPIMAGE) {
        options.execPath = runtime.env.APPIMAGE;
    }
    return options;
}

module.exports = { buildRelaunchOptions };
