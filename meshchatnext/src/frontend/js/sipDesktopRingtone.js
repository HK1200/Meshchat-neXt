// SPDX-License-Identifier: 0BSD
import { apiPath } from "./constants";
export function createSipDesktopRingtone(options = {}) {
    let generation = 0,
        activeId = null,
        player = null,
        context = null,
        interval = null;
    const schedule = options.setInterval || globalThis.setInterval;
    const unschedule = options.clearInterval || globalThis.clearInterval;
    function stop() {
        generation++;
        activeId = null;
        if (interval !== null) unschedule(interval);
        interval = null;
        if (player) {
            player.pause();
            player.currentTime = 0;
        }
        player = null;
        if (context) context.close().catch(() => {});
        context = null;
    }
    async function start(id) {
        if (activeId === id) return;
        stop();
        activeId = id;
        const token = generation;
        try {
            const getStatus =
                options.getStatus || (async () => (await window.api.get(apiPath("/telephone/ringtones/status"))).data);
            const status = await getStatus();
            if (generation !== token) return;
            if (status?.has_custom_ringtone && /^[a-z0-9_-]+$/i.test(String(status.id || ""))) {
                const Audio = options.Audio || globalThis.Audio;
                player = new Audio(apiPath(`/telephone/ringtones/${status.id}/audio`));
                player.loop = true;
                player.volume = Math.max(0, Math.min(1, Number(status.volume ?? 0.65)));
                await player.play();
                return;
            }
        } catch {
            /* A built-in tone remains available without a custom file. */
        }
        if (generation !== token) return;
        const AudioContext = options.AudioContext || globalThis.AudioContext || globalThis.webkitAudioContext;
        if (!AudioContext) return;
        let ownedContext;
        try {
            ownedContext = new AudioContext();
            context = ownedContext;
            await ownedContext.resume();
            if (generation !== token) return;
            function ring() {
                if (!context || generation !== token) return;
                const now = context.currentTime;
                for (const frequency of [440, 480]) {
                    const tone = context.createOscillator(),
                        gain = context.createGain();
                    tone.frequency.value = frequency;
                    gain.gain.setValueAtTime(0, now);
                    gain.gain.linearRampToValueAtTime(0.07, now + 0.02);
                    gain.gain.setValueAtTime(0.07, now + 1.8);
                    gain.gain.linearRampToValueAtTime(0, now + 2);
                    tone.connect(gain);
                    gain.connect(context.destination);
                    tone.start(now);
                    tone.stop(now + 2);
                }
            }
            ring();
            interval = schedule(ring, 5000);
        } catch {
            if (context === ownedContext) {
                context.close().catch(() => {});
                context = null;
            }
        }
    }
    return { start, stop };
}
