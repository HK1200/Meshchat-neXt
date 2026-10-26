import { checkUpdate } from "./api/update.js";

// Checks notify only; downloads and Android installation always need user action.
export function startAutomaticUpdates(onAvailable, { intervalMs = 6 * 60 * 60 * 1000 } = {}) {
    let stopped = false;
    let busy = false;
    let notifiedVersion = "";
    const check = async () => {
        if (stopped || busy) return;
        busy = true;
        try {
            const { data } = await checkUpdate();
            const version = data?.manifest?.version;
            if (!stopped && data?.enabled && data?.update_available && version && version !== notifiedVersion) {
                notifiedVersion = version;
                onAvailable(version);
            }
        } catch {
            // Offline starts and unavailable publishers must not interrupt the app.
        } finally {
            busy = false;
        }
    };
    const first = setTimeout(check, 15000);
    const timer = setInterval(check, intervalMs);
    return () => {
        stopped = true;
        clearTimeout(first);
        clearInterval(timer);
    };
}
