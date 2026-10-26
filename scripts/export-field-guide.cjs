// Generate the GitHub-readable guide from the same trusted, repository-owned content as the interactive edition.
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const folder = path.resolve(__dirname, "../docs/guide");
const context = { window: {} };
vm.runInNewContext(fs.readFileSync(path.join(folder, "content.js"), "utf8"), context, { timeout: 1000 });
const data = context.window.NEXT_GUIDE;
const lines = [
    "# Meshchat neXt · User guide",
    "Local release-guide draft, reviewed against the 2026-10-26 build. Features vary by platform, firmware and peer application. No public release is implied.",
    "## One app, independent services",
    "Reticulum → RNode / LAN / TCP → LXMF messages and LXST calls.\n\nMeshCore → separate companion → DMs, channels and TAC; optional Radio2 media.\n\nSIP → separate provider account → IP extension calls.\n\nContact linking groups addresses; it does not bridge networks.",
];
for (const article of data.articles)
    lines.push(
        "## " + article.title,
        article.lead,
        "### How to",
        article.steps.map((s, i) => `${i + 1}. ${s}`).join("\n"),
        "### Keep in mind",
        article.notes.map((s) => "- " + s).join("\n")
    );
lines.push("## FAQ / How do I?");
for (const [question, answer] of data.faqs) lines.push("### " + question, answer);
lines.push("## Glossary", ...Object.entries(data.glossary).map(([key, value]) => `- **${key}:** ${value}`));
lines.push("## Sources and compatibility references", ...data.sources.map(([name, url]) => `- [${name}](${url})`));
lines.push(
    "## Review boundaries",
    "This guide describes implemented UI and documented local validation; it does not claim hosted GitHub CI execution, an already-published release, exhaustive ATAK compatibility or a built-in firmware assistant. External projects and firmware change. Check the exact neXt release notes and hardware before flashing."
);
fs.writeFileSync(path.join(folder, "README.md"), lines.join("\n\n") + "\n");
