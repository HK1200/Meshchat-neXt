/** Short aliases locate candidates only; they never authenticate or link contacts. */
export function attachmentContacts(contacts, alias) {
    if (!/^[0-9a-f]{8}$/.test(alias || "")) return [];
    const seen = new Set();
    return (contacts || []).filter((contact) => {
        const key = contact?.peer;
        if (contact.active === false || !/^[0-9a-f]{64}$/.test(key || "") || !key.startsWith(alias) || seen.has(key))
            return false;
        seen.add(key);
        return true;
    });
}
