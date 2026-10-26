export function voiceEnvelope(text) {
    if (typeof text !== "string" || text.length > 160) return null;
    const fields = text.split(" ", 1)[0];
    if (!/^(VE3|VI1):[0-9a-z]{1,7}:[0-9a-z]{1,2}:[0-9a-z]{1,2}:[0-9a-z]{1,2}$/.test(fields)) return null;
    const [sid, mode, total, seconds] = fields
        .slice(4)
        .split(":")
        .map((x) => parseInt(x, 36));
    const image = fields.startsWith("VI1:");
    return sid > 0 &&
        sid <= 0xffffffff &&
        total >= 1 &&
        total <= 64 &&
        (image ? mode === 40 && seconds >= 1 && seconds <= 600 : mode <= 6 && seconds >= 1 && seconds <= 20)
        ? { sid: sid.toString(16).padStart(8, "0"), mode, total, seconds, ...(image ? { image: true } : {}) }
        : null;
}
export function channelMediaEnvelope(row) {
    const text = row?.direction === "in" ? row.text?.slice((row.text?.indexOf(": ") ?? -2) + 2) : row?.text;
    return voiceEnvelope(text);
}
export function imageUrl(encoded) {
    const bytes = Uint8Array.from(atob(encoded), (char) => char.charCodeAt(0));
    return URL.createObjectURL(new Blob([bytes], { type: "image/png" }));
}
export function mediaUrl(result) {
    return result.png_base64 ? imageUrl(result.png_base64) : audioUrl(result.wav_base64);
}
export function audioUrl(encoded) {
    const binary = atob(encoded);
    const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
    return URL.createObjectURL(new Blob([bytes], { type: "audio/wav" }));
}
export function pcmBase64(chunks, rate) {
    const size = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
    const source = new Int16Array(size);
    let offset = 0;
    for (const chunk of chunks) {
        source.set(chunk, offset);
        offset += chunk.length;
    }
    const length = Math.min(160000, Math.floor((size * 8000) / rate));
    if (length < 800) throw new Error("Record at least a moment before stopping.");
    const data = new Uint8Array(length * 2),
        view = new DataView(data.buffer);
    for (let index = 0; index < length; index++) {
        const start = Math.floor((index * rate) / 8000),
            end = Math.max(start + 1, Math.floor(((index + 1) * rate) / 8000));
        let sum = 0;
        for (let i = start; i < end && i < size; i++) sum += source[i];
        view.setInt16(index * 2, Math.round(sum / (end - start)), true);
    }
    let binary = "";
    for (let i = 0; i < data.length; i += 8192) binary += String.fromCharCode(...data.subarray(i, i + 8192));
    return btoa(binary);
}

export function voicePreview(text) {
    const meta = voiceEnvelope(text);
    return meta ? (meta.image ? "Photo · MeshCore Radio2" : `Voice clip · ${meta.seconds} seconds`) : text;
}
