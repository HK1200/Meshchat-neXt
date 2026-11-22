// SPDX-License-Identifier: 0BSD
// Discovery can contain IFAC credentials and coordinates. Transfer the draft
// only within this running app; never serialize it into browser storage.
const LEGACY_KEY = "meshchatnext.discoveredInterfacePrefill";
let pending = null;

function clearLegacyDraft() {
    try {
        globalThis.sessionStorage?.removeItem(LEGACY_KEY);
    } catch {
        // Private browsing may deny storage; the in-memory transfer still works.
    }
}

export function stageDiscoveredInterfaceDraft(draft) {
    clearLegacyDraft();
    pending = { ...draft };
}

export function takeDiscoveredInterfaceDraft() {
    clearLegacyDraft();
    const draft = pending;
    pending = null;
    return draft;
}
