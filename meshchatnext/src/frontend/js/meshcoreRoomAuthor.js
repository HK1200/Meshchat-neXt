/** A room's four-byte author prefix is a display hint, never authentication. */
export function roomAuthor(signature, contacts = []) {
    if (typeof signature !== "string" || !/^[a-f0-9]{8}$/i.test(signature))
        return { label: "Unknown author", prefix: "", matched: false };
    const prefix = signature.toLowerCase();
    const candidates = new Map();
    for (const contact of contacts || []) {
        const key = typeof contact?.peer === "string" ? contact.peer.toLowerCase() : "";
        if (contact.active === false || contact.active === 0 || !/^[a-f0-9]{64}$/.test(key) || !key.startsWith(prefix))
            continue;
        candidates.set(key, contact);
    }
    if (candidates.size === 1) {
        const name = [...candidates.values()][0].name;
        if (typeof name === "string" && name.trim()) return { label: name.trim(), prefix, matched: true };
    }
    return { label: `Author ${prefix}`, prefix, matched: false };
}
