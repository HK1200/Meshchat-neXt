// SPDX-License-Identifier: MIT
import Utils from "./Utils";

// Advert times come from remote clocks; receipt times come from this device.
export function formatMeshcoreAge(seconds) {
    if (typeof seconds !== "number" || !Number.isFinite(seconds) || seconds <= 0) return "time unknown";
    if (seconds > Date.now() / 1000 + 60) return "clock ahead · time unreliable";
    return Utils.formatTimeAgo(new Date(seconds * 1000));
}
