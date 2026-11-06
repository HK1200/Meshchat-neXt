/** Plain-text room context, not a private message or authenticated mention. */
function line(value) {
    return String(value ?? "")
        .replace(/[\p{Cc}\u202a-\u202e\u2066-\u2069]/gu, " ")
        .replace(/\s+/g, " ")
        .trim();
}
function limit(value, bytes) {
    let result = "";
    for (const character of value) {
        if (new TextEncoder().encode(result + character).length > bytes) break;
        result += character;
    }
    return result;
}
export function roomReply(row, author) {
    const label = limit(line(author.label), 24) || "Unknown author";
    const prefix = /^[a-f0-9]{8}$/.test(author.prefix || "") ? ` [${author.prefix}]` : "";
    const excerpt = limit(line(row.text), 32);
    return { id: row.id, label, header: `> ${label}${prefix}: ${excerpt}\n` };
}
export function roomPostText(draft, reply) {
    return reply ? reply.header + draft : draft;
}
