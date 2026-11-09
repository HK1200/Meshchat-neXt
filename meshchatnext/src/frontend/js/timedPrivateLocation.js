// SPDX-License-Identifier: 0BSD

import { shallowReactive } from "vue";
import { getAndroidPosition } from "./androidLocation.js";

export const privateLocationSessions = shallowReactive(new Map());

export function startPrivateLocationSession(key, name, options) {
    if (privateLocationSessions.has(key)) return;
    const stop = repeatPrivateLocation({
        ...options,
        onStop(reason) {
            privateLocationSessions.delete(key);
            options.onStop?.(reason);
        },
    });
    privateLocationSessions.set(key, { name, stop });
}

export function stopAllPrivateLocationSessions() {
    for (const { stop } of privateLocationSessions.values()) stop();
}

export async function readPrivateLocation(source, config = {}, timeout = 30000) {
    if (source === "manual") {
        return {
            latitude: parseFloat(config.location_manual_lat),
            longitude: parseFloat(config.location_manual_lon),
            altitude: parseFloat(config.location_manual_alt),
        };
    }
    if (source === "android") return getAndroidPosition();

    const fix = await new Promise((resolve, reject) => {
        if (!navigator.geolocation) {
            reject(new Error("Geolocation unavailable"));
            return;
        }
        navigator.geolocation.getCurrentPosition(resolve, reject, {
            enableHighAccuracy: true,
            timeout,
            maximumAge: 0,
        });
    });
    return {
        latitude: fix.coords.latitude,
        longitude: fix.coords.longitude,
        altitude: fix.coords.altitude,
        accuracy: fix.coords.accuracy,
        speed: fix.coords.speed,
        bearing: fix.coords.heading,
        time: fix.timestamp,
    };
}

const SAMPLE_MS = 60_000;
const STILL_UPDATE_MS = 300_000;

function moved(previous, current) {
    const radians = Math.PI / 180;
    const dLat = (current.latitude - previous.latitude) * radians;
    const dLon = (current.longitude - previous.longitude) * radians;
    const arc =
        Math.sin(dLat / 2) ** 2 +
        Math.cos(previous.latitude * radians) * Math.cos(current.latitude * radians) * Math.sin(dLon / 2) ** 2;
    const distance = 12_742_000 * Math.asin(Math.sqrt(Math.min(1, arc)));
    return distance >= Math.max(50, (previous.accuracy || 0) + (current.accuracy || 0));
}

// The caller sends the first fix after confirmation. The returned function
// cancels future sends, including a GPS fix that is still being obtained.
export function repeatPrivateLocation({ deadline, firstFix, getFix, sendFix, isCurrent, onStop }) {
    let lastFix = firstFix;
    let lastSent = Date.now();
    let timer;
    let stopped = false;

    function stop(reason = "stopped") {
        if (stopped) return;
        stopped = true;
        clearTimeout(timer);
        document.removeEventListener("visibilitychange", onVisibility);
        onStop(reason);
    }

    function onVisibility() {
        if (document.hidden) stop();
    }

    function canContinue() {
        if (stopped) return false;
        if (Date.now() >= deadline) {
            stop("expired");
            return false;
        }
        if (document.hidden || !isCurrent()) {
            stop();
            return false;
        }
        return true;
    }

    function schedule() {
        timer = setTimeout(tick, Math.min(SAMPLE_MS, Math.max(0, deadline - Date.now())));
    }

    async function tick() {
        if (!canContinue()) return;
        try {
            const fix = await getFix();
            if (!canContinue()) return;
            const now = Date.now();
            const fresh = !fix.time || now - fix.time <= 120_000;
            if (fresh && (moved(lastFix, fix) || now - lastSent >= STILL_UPDATE_MS)) {
                await sendFix(fix);
                lastFix = fix;
                lastSent = Date.now();
            }
        } catch {
            stop("error");
            return;
        }
        if (canContinue()) schedule();
    }

    document.addEventListener("visibilitychange", onVisibility);
    schedule();
    return stop;
}
