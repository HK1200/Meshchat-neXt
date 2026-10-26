/* Meshchat neXt interactive guide. No network requests or app API calls. */
(() => {
    "use strict";
    const D = window.NEXT_GUIDE;
    const reader = document.getElementById("reader"),
        nav = document.getElementById("navigation"),
        search = document.getElementById("search"),
        result = document.getElementById("results");
    let path = "all",
        query = "";
    function el(tag, text, cls) {
        const n = document.createElement(tag);
        if (text !== undefined) n.textContent = text;
        if (cls) n.className = cls;
        return n;
    }
    function link(text, href, cls) {
        const n = el("a", text, cls);
        n.href = href;
        return n;
    }
    function button(text, fn, cls) {
        const n = el("button", text, cls);
        n.type = "button";
        n.addEventListener("click", fn);
        return n;
    }
    function append(parent, ...nodes) {
        for (const n of nodes) parent.append(n);
        return parent;
    }
    function read(key, fallback) {
        try {
            return JSON.parse(localStorage.getItem(key)) ?? fallback;
        } catch {
            return fallback;
        }
    }
    function save(key, value) {
        try {
            localStorage.setItem(key, JSON.stringify(value));
        } catch {
            /* The guide still works when storage is unavailable. */
        }
    }
    const progress = read("meshchat-next.guide-progress.v1", {});
    if (read("meshchat-next.guide-theme", "") === "light") document.body.classList.add("light");
    document.getElementById("theme").addEventListener("click", () => {
        document.body.classList.toggle("light");
        save("meshchat-next.guide-theme", document.body.classList.contains("light") ? "light" : "dark");
    });
    document.getElementById("topics").addEventListener("click", () => {
        const open = nav.classList.toggle("mobile-open");
        document.getElementById("topics").setAttribute("aria-expanded", String(open));
    });
    document.getElementById("print").addEventListener("click", () => window.print());
    document.addEventListener("keydown", (e) => {
        if (e.key === "/" && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) {
            e.preventDefault();
            search.focus();
        }
    });
    function matches(a) {
        return !query || [a.title, a.group, a.lead, ...a.steps, ...a.notes].join(" ").toLowerCase().includes(query);
    }
    function heading(title, kicker, lead) {
        append(reader, el("div", kicker, "eyebrow"), el("h1", title));
        if (lead) reader.append(el("p", lead, "lead"));
    }
    function drawNav(id) {
        nav.replaceChildren();
        append(
            nav,
            link("Overview & starting paths", "#home"),
            link("FAQ / How do I?", "#faq"),
            link("Glossary", "#glossary"),
            link("Compatibility at a glance", "#compatibility")
        );
        for (const group of ["Essentials", "Reticulum", "MeshCore", "TAC & maps", "SIP", "More tools"]) {
            const rows = D.articles.filter((a) => a.group === group && matches(a));
            if (!rows.length) continue;
            nav.append(el("h2", group));
            for (const a of rows) {
                const l = link(a.title, "#article/" + a.id);
                if (id === a.id) l.setAttribute("aria-current", "page");
                nav.append(l);
            }
        }
        nav.append(link("Sources & review limits", "#sources"));
    }
    function diagram() {
        const box = el("div", undefined, "network-map");
        box.setAttribute("role", "img");
        box.setAttribute(
            "aria-label",
            "Independent paths: Reticulum connects through RNode, LAN or TCP to LXMF and LXST peers. MeshCore connects through a separate companion to its peers and TAC team data. SIP uses its own provider. No automatic bridge joins them."
        );
        box.append(el("div", "One interface. Independent connections.", "map-head"));
        for (const [cls, badge, left, leftSub, right, rightSub] of [
            [
                "rns",
                "RETICULUM",
                "RNode / LAN / TCP",
                "Your Reticulum identity",
                "LXMF · LXST",
                "Messages & live calls",
            ],
            [
                "mc",
                "MESHCORE",
                "Separate companion",
                "Your radio’s MeshCore identity",
                "MeshCore peers",
                "DMs, channels & node tools",
            ],
            [
                "tac",
                "TAC / MAPS",
                "Private team channel",
                "Carried over MeshCore",
                "Team map & reports",
                "Optional Radio2 attachments",
            ],
            [
                "sip",
                "SIP",
                "IP network + provider",
                "Your extension account",
                "SIP extensions",
                "Separate live calling",
            ],
        ]) {
            const row = el("div", undefined, "lane " + cls);
            append(
                row,
                el("div", badge, "badge"),
                append(el("div", undefined, "node"), el("strong", left), el("small", leftSub)),
                el("span", "→"),
                append(el("div", undefined, "node"), el("strong", right), el("small", rightSub))
            );
            box.append(row);
        }
        return box;
    }
    function cards(ids) {
        const grid = el("div", undefined, "cards");
        for (const [i, id] of ids.entries()) {
            const a = D.articles.find((a) => a.id === id);
            if (!a) continue;
            append(
                grid,
                append(
                    link("", "#article/" + id, "card"),
                    el("span", String(i + 1).padStart(2, "0") + " / " + a.group.toUpperCase(), "num"),
                    el("h3", a.title),
                    el("p", a.lead)
                )
            );
        }
        return grid;
    }
    function home() {
        heading(
            "Find your way. Stay connected.",
            "A practical guide to Meshchat neXt",
            "New to the mesh, bringing an existing setup, or adding a new service? Start with the path that fits you. Everything here is readable offline once the guide is on your device."
        );
        const stats = el("div", undefined, "stats");
        for (const [num, label] of [
            [D.articles.length, "practical articles"],
            [D.faqs.length, "questions answered"],
            ["3", "independent services"],
        ])
            stats.append(append(el("span"), el("strong", String(num)), el("span", label)));
        reader.append(
            stats,
            diagram(),
            el(
                "p",
                "A shared contact can hold several addresses. Linking those addresses does not bridge the networks.",
                "caption"
            )
        );
        reader.append(el("h2", "What brings you here?"));
        const picker = el("div", undefined, "path-picker");
        for (const [id, v] of Object.entries(D.paths)) {
            const b = button(v.label, () => {
                path = id;
                render();
            });
            b.setAttribute("aria-pressed", String(path === id));
            picker.append(b);
        }
        reader.append(picker, el("p", D.paths[path].intro, "path-info"), cards(D.paths[path].ids));
        const box = append(
            el("div", undefined, "callout warning"),
            el("strong", "Start small. Add more when you’re ready."),
            el(
                "span",
                "You do not need both radios or every service. Prove a text message or extension call works before adding media, maps or multiple interfaces."
            )
        );
        reader.append(
            box,
            append(
                el("div", undefined, "section-links"),
                link("FAQ / How do I? →", "#faq"),
                link("Who can I talk to? →", "#compatibility"),
                link("Get community help →", "#article/support")
            )
        );
    }
    function article(id) {
        const a = D.articles.find((a) => a.id === id);
        if (!a) {
            heading("Topic not found", "Guide");
            reader.append(link("Return to the guide", "#home"));
            return;
        }
        reader.append(link("← All starting paths", "#home", "crumb"));
        heading(a.title, a.group, a.lead);
        if (id === "start" || id === "interop") reader.append(diagram());
        reader.append(el("h2", "Step by step"));
        const list = el("ol", undefined, "steps");
        for (const s of a.steps) list.append(el("li", s));
        reader.append(list, el("h2", "Keep in mind"));
        const notes = el("ul", undefined, "notes");
        for (const n of a.notes) notes.append(el("li", n));
        reader.append(notes);
        const check = el("div", undefined, "checklist");
        check.append(
            el("h3", "My progress"),
            el(
                "p",
                "A personal reading checklist, not a check of your actual device. Saved only in this browser.",
                "muted small"
            )
        );
        const status = el("span"),
            bar = el("progress");
        bar.max = a.steps.length;
        const line = append(el("div", undefined, "progress"), status, el("span", "LOCAL ONLY"));
        check.append(line, bar);
        const update = () => {
            const count = a.steps.filter((_, i) => progress[a.id + ":" + i]).length;
            status.textContent = count + " of " + a.steps.length + " steps checked";
            bar.value = count;
        };
        a.steps.forEach((s, i) => {
            const input = el("input");
            input.type = "checkbox";
            input.checked = Boolean(progress[a.id + ":" + i]);
            input.addEventListener("change", () => {
                progress[a.id + ":" + i] = input.checked;
                save("meshchat-next.guide-progress.v1", progress);
                update();
            });
            check.append(append(el("label"), input, el("span", s)));
        });
        update();
        reader.append(check);
        const act = el("div", undefined, "article-actions");
        act.append(
            button("Copy topic link", async () => {
                try {
                    await navigator.clipboard.writeText(location.href);
                    act.querySelector("button").textContent = "Topic link copied";
                } catch {
                    act.querySelector("button").textContent = "Copy the address from your browser";
                }
            })
        );
        reader.append(act);
        const i = D.articles.indexOf(a),
            foot = el("div", undefined, "article-footer");
        reader.append(
            el(
                "p",
                "Browse guide chapters — this is reference navigation, not a required setup sequence.",
                "muted small"
            )
        );
        if (i > 0) foot.append(link("← " + D.articles[i - 1].title, "#article/" + D.articles[i - 1].id));
        if (i < D.articles.length - 1)
            foot.append(link(D.articles[i + 1].title + " →", "#article/" + D.articles[i + 1].id));
        reader.append(foot);
    }
    function faq() {
        heading(
            "How do I…?",
            "FAQ",
            "Plain answers to the questions that appear when several ecosystems meet in one app. Search above to narrow these down."
        );
        const rows = D.faqs.filter((row) => !query || row.join(" ").toLowerCase().includes(query));
        const container = el("div", undefined, "faq");
        for (const [q, a, id] of rows) {
            const details = el("details");
            append(
                details,
                el("summary", q),
                append(el("div"), el("p", a), link("Show me the steps →", "#article/" + id))
            );
            container.append(details);
        }
        reader.append(
            rows.length
                ? container
                : el("p", "No matching questions. Try “radio”, “backup”, “call” or “offline”.", "empty")
        );
    }
    function glossary() {
        heading(
            "A few useful words.",
            "Glossary",
            "You do not need to learn every acronym before starting. Look one up when it gets in your way."
        );
        const dl = el("dl", undefined, "glossary");
        for (const [k, v] of Object.entries(D.glossary).filter(
            ([k, v]) => !query || (k + " " + v).toLowerCase().includes(query)
        ))
            dl.append(append(el("div"), el("dt", k), el("dd", v)));
        reader.append(dl);
    }
    function compatibility() {
        heading(
            "Compatibility follows the protocol.",
            "Interoperability",
            "Sharing a radio technology or a map icon does not make two systems interchangeable. Start with the message type you need."
        );
        reader.append(diagram(), el("h2", "At a glance"));
        const wrap = el("div", undefined, "table-wrap"),
            table = el("table"),
            head = el("tr");
        for (const h of ["In neXt", "Other endpoint", "What to check"]) head.append(el("th", h));
        table.append(append(el("thead"), head));
        const body = el("tbody");
        for (const row of [
            [
                "Reticulum / LXMF text",
                "Sideband, NomadNet, compatible LXMF clients",
                "Reachable destination; rich-content support varies.",
            ],
            [
                "Reticulum / LXST calls",
                "Compatible LXST telephone peer",
                "A messaging-only peer is not automatically callable.",
            ],
            [
                "MeshCore text",
                "Compatible MeshCore apps + companions",
                "Primary radio profile, full key / channel key, scope.",
            ],
            [
                "Radio2 media",
                "MeshCore Open TAK / VOX tested",
                "Codec2 1200 / standard photos, compatible firmware and media profile. RF media is unencrypted.",
            ],
            [
                "Tactical maps & reports",
                "Selected Open TAK / TAK formats",
                "Check the article for direction-specific validation and limits.",
            ],
            [
                "SIP / HOIP",
                "Provider-compatible clients, including Linphone tested",
                "Own extension/server, permitted route, incoming call and audio test.",
            ],
            ["Meshtastic", "Different mesh protocol", "No direct protocol interoperability or automatic gateway."],
        ]) {
            const tr = el("tr");
            row.forEach((v) => tr.append(el("td", v)));
            body.append(tr);
        }
        table.append(body);
        wrap.append(table);
        reader.append(
            wrap,
            append(
                el("div", undefined, "callout warning"),
                el("strong", "Tested is specific. Compatibility is not universal."),
                el(
                    "span",
                    "A successful test with one firmware, codec or package does not cover every app release, server or tactical datatype."
                )
            ),
            cards(["interop", "tak", "radio2"])
        );
    }
    function sources() {
        heading(
            "Built from the app. Checked against the protocols.",
            "Sources & review limits",
            "This is a local release-guide draft, not a claim that a public release or hosted CI run has happened."
        );
        reader.append(
            el(
                "p",
                "Menus, defaults and validation notes were checked against the current neXt source and local development records on 26 October 2026. External projects can change; use the release notes for your exact build.",
                "muted"
            )
        );
        const list = el("ul", undefined, "source-list");
        for (const [name, url] of D.sources) {
            const a = link(name + " ↗", url);
            a.target = "_blank";
            a.rel = "noopener noreferrer";
            list.append(append(el("li"), a));
        }
        reader.append(
            list,
            append(
                el("div", undefined, "callout"),
                el("strong", "What this guide does not promise"),
                el(
                    "span",
                    "No built-in firmware assistant; no automatic service bridging; no live MeshCore telephone; no exhaustive ATAK or arbitrary-provider certification; no guaranteed offline coverage or battery life. Platform, firmware and network constraints still apply."
                )
            ),
            link("Read the complete Markdown edition", "README.md")
        );
    }
    function searchView() {
        heading(
            "Find an answer.",
            "Search",
            "Results for “" + search.value + "”. Nothing is sent to a search service."
        );
        const found = D.articles.filter(matches),
            fa = D.faqs.filter((r) => r.join(" ").toLowerCase().includes(query));
        result.textContent = found.length + " topics · " + fa.length + " questions";
        if (found.length) reader.append(cards(found.map((a) => a.id)));
        if (fa.length) {
            reader.append(el("h2", "Questions"));
            const box = el("div", undefined, "faq");
            for (const [q, a, id] of fa) {
                box.append(
                    append(
                        el("details"),
                        el("summary", q),
                        append(el("div"), el("p", a), link("Read the walkthrough →", "#article/" + id))
                    )
                );
            }
            reader.append(box);
        }
        if (!found.length && !fa.length)
            reader.append(el("p", "No match. Try a service name or a shorter term.", "empty"));
    }
    function render() {
        reader.replaceChildren();
        const route = location.hash.slice(1) || "home";
        drawNav(route.startsWith("article/") ? route.slice(8) : "");
        result.textContent = query ? "" : "Browse all " + D.articles.length + " topics";
        if (query) searchView();
        else if (route.startsWith("article/")) article(route.slice(8));
        else if (route === "faq") faq();
        else if (route === "glossary") glossary();
        else if (route === "compatibility") compatibility();
        else if (route === "sources") sources();
        else home();
        document.title = (reader.querySelector("h1")?.textContent || "Field guide") + " · Meshchat neXt";
    }
    search.addEventListener("input", () => {
        query = search.value.trim().toLowerCase();
        render();
    });
    window.addEventListener("hashchange", () => {
        query = "";
        search.value = "";
        nav.classList.remove("mobile-open");
        document.getElementById("topics").setAttribute("aria-expanded", "false");
        render();
        window.scrollTo({ top: 0 });
    });
    render();
})();
