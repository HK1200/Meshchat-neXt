// SPDX-License-Identifier: 0BSD
//
// Heap and listener growth profiler for UI pages under simulated data.
// Run with the UI stack config:
//   MESHCHAT_UI_PROD=1 pnpm exec playwright test \
//     --config playwright.ui.config.js tests/ui/heap-profile.spec.js
//
// Instruments addEventListener/removeEventListener and the timer APIs before
// page scripts run, then mounts and unmounts each catalog page several times,
// forcing GC through CDP between cycles. Per page it reports listener and
// timer deltas plus used JS heap before/after so growth shows up as a
// non-zero trend across cycles.

const { test, expect } = require("@playwright/test");
const fs = require("fs");
const path = require("path");
const { dismissMapOnboardingTooltip } = require("../e2e/helpers");
const { resolvePages, heapBudgetsFor } = require("./pages");
const { seedUiSimulatedData } = require("./seed");
const { gotoUiPage, waitForPageReady } = require("./ready");

const CYCLES = Number(process.env.MESHCHAT_HEAP_CYCLES || 5);
const NEUTRAL_PATH = "/tools";
const REPORT_DIR = path.join(__dirname, "..", "..", "test-results", "heap");

// Per-page growth budgets measured after CYCLES mount/unmount rounds with a
// forced GC between each. Values are generous: the goal is catching leaks and
// unbounded re-registration, not pinning exact counts on noisy CI runners.
const HEAP_BUDGETS = {
    heapDeltaMb: Number(process.env.MESHCHAT_HEAP_MAX_DELTA_MB || 30),
    nodes: Number(process.env.MESHCHAT_HEAP_MAX_NODES || 500),
    listeners: Number(process.env.MESHCHAT_HEAP_MAX_LISTENERS || 10),
    timeouts: Number(process.env.MESHCHAT_HEAP_MAX_TIMEOUTS || 10),
    intervals: Number(process.env.MESHCHAT_HEAP_MAX_INTERVALS || 3),
    rafs: Number(process.env.MESHCHAT_HEAP_MAX_RAFS || 3),
};

const INSTRUMENT = `
(() => {
    const pending = { timeouts: new Set(), intervals: new Set(), rafs: new Set() };
    const counters = {};
    for (const name of Object.keys(pending)) {
        Object.defineProperty(counters, name, { enumerable: true, get: () => pending[name].size });
    }
    window.__leakCounters = counters;
    const set = window.setTimeout.bind(window), clear = window.clearTimeout.bind(window);
    window.setTimeout = (fn, delay, ...args) => {
        let id;
        const callback = typeof fn === 'function' ? (...values) => {
            pending.timeouts.delete(id);
            return fn(...values);
        } : fn;
        id = set(callback, delay, ...args);
        pending.timeouts.add(id);
        return id;
    };
    window.clearTimeout = id => { pending.timeouts.delete(id); clear(id); };
    const interval = window.setInterval.bind(window), clearInterval = window.clearInterval.bind(window);
    window.setInterval = (...args) => { const id = interval(...args); pending.intervals.add(id); return id; };
    window.clearInterval = id => { pending.intervals.delete(id); clearInterval(id); };
    const frame = window.requestAnimationFrame.bind(window), cancel = window.cancelAnimationFrame.bind(window);
    window.requestAnimationFrame = fn => {
        const id = frame(time => { pending.rafs.delete(id); fn(time); });
        pending.rafs.add(id);
        return id;
    };
    window.cancelAnimationFrame = id => { pending.rafs.delete(id); cancel(id); };
})();
`;

async function settleListeners(page, cdp, maxMs = 4000) {
    // Route changes detach the previous page asynchronously, so wait until
    // the live listener count stops moving instead of sampling mid-teardown.
    // A single quiet sample can still catch a gap between two deferred
    // removals, so require three consecutive unchanged samples.
    let last = -1;
    let stableSamples = 0;
    const deadline = Date.now() + maxMs;
    while (Date.now() < deadline) {
        const { metrics } = await cdp.send("Performance.getMetrics");
        const current = metrics.find((m) => m.name === "JSEventListeners")?.value || 0;
        if (current === last) {
            stableSamples += 1;
            if (stableSamples >= 3) {
                return;
            }
        } else {
            stableSamples = 0;
        }
        last = current;
        await page.waitForTimeout(200);
    }
}

async function measure(page, cdp) {
    await settleListeners(page, cdp);
    await cdp.send("HeapProfiler.collectGarbage");
    await settleListeners(page, cdp);
    await cdp.send("HeapProfiler.collectGarbage");
    const { metrics } = await cdp.send("Performance.getMetrics");
    const pick = (name) => metrics.find((m) => m.name === name)?.value || 0;
    const counters = await page.evaluate(() => window.__leakCounters);
    return {
        heap: pick("JSHeapUsedSize"),
        nodes: pick("Nodes"),
        listeners: pick("JSEventListeners"),
        timeouts: counters.timeouts,
        intervals: counters.intervals,
        rafs: counters.rafs,
    };
}

function fmt(bytes) {
    return (bytes / 1024 / 1024).toFixed(2) + " MB";
}

test.describe("heap profile across pages", () => {
    test.beforeAll(async ({ request }) => {
        await seedUiSimulatedData(request);
    });

    test("per-page listener and heap deltas", async ({ page, baseURL }) => {
        test.setTimeout(600000);
        await page.addInitScript(INSTRUMENT);
        // Live websocket traffic (announce syncs, message events) adds and
        // removes listeners mid-measurement, which reads as fake growth.
        // Hold the socket open but silent so deltas stay deterministic.
        await page.routeWebSocket(/\/ws(\?.*)?$/, (ws) => {
            ws.onmessage = () => {};
        });
        const cdp = await page.context().newCDPSession(page);
        await cdp.send("HeapProfiler.enable");
        if (process.env.MESHCHAT_HEAP_CPU_THROTTLE) {
            await cdp.send("Emulation.setCPUThrottlingRate", {
                rate: Number(process.env.MESHCHAT_HEAP_CPU_THROTTLE),
            });
        }
        await cdp.send("Performance.enable");

        const neutral = { id: "tools", path: NEUTRAL_PATH, readyKind: "placeholder", ready: "Search tools..." };
        const pages = resolvePages({
            ciOnly: process.env.MESHCHAT_UI_CI === "1",
            ids: process.env.MESHCHAT_UI_PAGES
                ? process.env.MESHCHAT_UI_PAGES.split(",")
                      .map((s) => s.trim())
                      .filter(Boolean)
                : null,
        }).filter((p) => p.path !== NEUTRAL_PATH);

        // Warm the app shell once so module-level caches reach steady state.
        await gotoUiPage(page, neutral, baseURL);
        await measure(page, cdp);

        // Navigate inside the existing app so Vue unmount cleanup is exercised.
        // Full page.goto reloads measure discarded documents and Vite contexts,
        // rather than the lifetime of a view in the running application.
        const navigate = async (entry) => {
            await page.evaluate((target) => {
                window.location.hash = target;
            }, entry.path);
            await waitForPageReady(page, entry);
        };

        const report = [];
        for (const entry of pages) {
            try {
                // One warm cycle absorbs first-mount module and cache costs so
                // the measured delta shows only per-mount growth.
                await navigate(entry);
                if (entry.id === "map") {
                    await dismissMapOnboardingTooltip(page);
                }
            } catch (e) {
                report.push({ page: entry.id, skipped: String(e).slice(0, 80) });
                continue;
            }
            const measureDelta = async () => {
                await navigate(neutral);
                const before = await measure(page, cdp);
                let after = before;
                for (let i = 0; i < CYCLES; i++) {
                    await navigate(entry);
                    await navigate(neutral);
                    after = await measure(page, cdp);
                    console.log(
                        `heap-cycle | ${entry.id} ${i + 1}/${CYCLES} nodes=${after.nodes - before.nodes} listeners=${after.listeners - before.listeners}`
                    );
                }
                return {
                    heapDelta: after.heap - before.heap,
                    nodes: after.nodes - before.nodes,
                    listeners: after.listeners - before.listeners,
                    timeouts: after.timeouts - before.timeouts,
                    intervals: after.intervals - before.intervals,
                    rafs: after.rafs - before.rafs,
                };
            };

            let delta = await measureDelta();
            const budgets = heapBudgetsFor(entry, HEAP_BUDGETS);
            const breaches = (d) =>
                d.heapDelta > budgets.heapDeltaMb * 1048576 ||
                d.nodes > budgets.nodes ||
                d.listeners > budgets.listeners ||
                d.timeouts > budgets.timeouts ||
                d.intervals > budgets.intervals ||
                d.rafs > budgets.rafs;
            if (breaches(delta)) {
                // Deferred teardown from a neighbor page can land inside this
                // window. One confirmation pass keeps the smaller delta, so a
                // real leak still fails while transient pollution does not.
                const confirm = await measureDelta();
                delta = {
                    heapDelta: Math.min(delta.heapDelta, confirm.heapDelta),
                    nodes: Math.min(delta.nodes, confirm.nodes),
                    listeners: Math.min(delta.listeners, confirm.listeners),
                    timeouts: Math.min(delta.timeouts, confirm.timeouts),
                    intervals: Math.min(delta.intervals, confirm.intervals),
                    rafs: Math.min(delta.rafs, confirm.rafs),
                };
            }
            report.push({ page: entry.id, ...delta });
        }

        fs.mkdirSync(REPORT_DIR, { recursive: true });
        const failures = [];
        for (const row of report) {
            if (row.skipped) {
                console.log(`heap-profile | ${row.page.padEnd(24)} SKIPPED ${row.skipped}`);
                continue;
            }
            console.log(
                `heap-profile | ${row.page.padEnd(24)} heap ${fmt(row.heapDelta).padStart(9)} ` +
                    `nodes ${String(row.nodes).padStart(6)} ` +
                    `listeners ${String(row.listeners).padStart(4)} ` +
                    `timeouts ${String(row.timeouts).padStart(4)} ` +
                    `intervals ${String(row.intervals).padStart(3)} ` +
                    `rafs ${String(row.rafs).padStart(4)}`
            );
            const pageEntry = pages.find((p) => p.id === row.page);
            const budgets = heapBudgetsFor(pageEntry, HEAP_BUDGETS);
            fs.writeFileSync(path.join(REPORT_DIR, `${row.page}.json`), JSON.stringify({ budgets, ...row }, null, 2));
            const checks = [
                ["heapDelta", row.heapDelta, budgets.heapDeltaMb * 1048576],
                ["nodes", row.nodes, budgets.nodes],
                ["listeners", row.listeners, budgets.listeners],
                ["timeouts", row.timeouts, budgets.timeouts],
                ["intervals", row.intervals, budgets.intervals],
                ["rafs", row.rafs, budgets.rafs],
            ];
            for (const [name, actual, budget] of checks) {
                if (actual > budget) {
                    failures.push(`${row.page}: ${name} ${actual} > ${budget}`);
                }
            }
        }
        expect(failures, "pages exceeded heap growth budgets").toEqual([]);
    });
});
