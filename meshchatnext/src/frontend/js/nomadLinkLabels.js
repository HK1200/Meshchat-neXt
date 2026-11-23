// SPDX-License-Identifier: 0BSD
// Put the accessible name on the actionable link. WebKit otherwise uses the
// clipped screen-reader span after its visible text as the link's hit region.
export function labelNomadLinks(root) {
    if (root?.nodeType !== 1 || typeof root.querySelectorAll !== "function") return;
    const selector = [
        "a.Mu-nl > .Mu-sr",
        "a.nomadnet-link > .Mu-sr",
        "a.lxmf-link > .Mu-sr",
        'a[data-action="openNode"] > .Mu-sr',
    ].join(",");
    for (const plain of root.querySelectorAll(selector)) {
        const link = plain.parentElement;
        const label = plain.textContent || "";
        if (!label.trim()) continue;
        if (!link.hasAttribute("aria-label") && !link.hasAttribute("aria-labelledby")) {
            link.setAttribute("aria-label", label);
        }
        // Keep the original span/visual glyphs and all routing attributes.
        // The explicit link name now provides the same plain spoken text.
        plain.setAttribute("aria-hidden", "true");
    }
}
