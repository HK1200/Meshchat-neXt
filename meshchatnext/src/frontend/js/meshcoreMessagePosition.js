import { computed, ref, watch, nextTick, onMounted, onBeforeUnmount } from "vue";
import { apiPath } from "./constants";
const sorted = (rows) => [...rows].sort((a, b) => a.created - b.created || a.id.localeCompare(b.id));
export function firstUnreadTarget(rows, view) {
    if (view?.first_unread?.id) return view.first_unread.id;
    return rows.find((row) => row.direction === "in" && row.created > (view?.seen || 0))?.id || null;
}
export function useMeshCoreMessagePosition({ snapshot, target, kind, list, rows, markRead, visit = () => "" }) {
    const windowRows = ref(null),
        firstUnreadId = ref(null),
        loading = ref(false),
        positionError = ref("");
    const visibleRows = computed(() => windowRows.value || rows.value);
    const hasNewer = computed(
        () =>
            windowRows.value?.length &&
            rows.value.length &&
            sorted(rows.value).at(-1).created > sorted(windowRows.value).at(-1)?.created
    );
    let scope = "",
        ready = false,
        stopped = false,
        revision = 0,
        timer,
        nearBottom = true,
        marked = 0,
        lastTail = null;
    const foreground = () => document.visibilityState === "visible" && document.hasFocus();
    let previousForeground = foreground();
    const key = () =>
        snapshot.value.owner && target() ? `meshcore-view:${snapshot.value.owner}:${kind}:${target()}` : "";
    const articles = () => [...(list.value?.querySelectorAll("[data-message-id]") || [])];
    function save() {
        if (!scope || !ready || !list.value) return;
        const rect = list.value.getBoundingClientRect();
        if (!rect.height) return;
        const row = articles().find((node) => node.getBoundingClientRect().bottom > rect.top);
        if (!row) return;
        try {
            localStorage.setItem(
                scope,
                JSON.stringify({ id: row.dataset.messageId, offset: row.getBoundingClientRect().top - rect.top })
            );
        } catch {
            /* Storage may be unavailable. */
        }
    }
    function readVisible() {
        if (!ready || stopped || !foreground() || !list.value) return;
        const rect = list.value.getBoundingClientRect();
        if (!rect.height) return;
        const ids = new Set(
            articles()
                .filter((node) => {
                    const box = node.getBoundingClientRect();
                    return box.height > 0 && box.bottom > rect.top && box.bottom <= rect.bottom + 1;
                })
                .map((node) => node.dataset.messageId)
        );
        const through = Math.max(0, ...visibleRows.value.filter((row) => ids.has(row.id)).map((row) => row.created));
        if (through > marked) {
            marked = through;
            Promise.resolve(markRead(through)).catch(() => {
                marked = 0;
            });
        }
    }
    function onScroll() {
        if (!ready || !list.value) return;
        nearBottom = list.value.scrollHeight - list.value.scrollTop - list.value.clientHeight < 50;
        clearTimeout(timer);
        timer = setTimeout(() => {
            save();
            readVisible();
        }, 100);
    }
    async function fetchWindow(options) {
        const { data } = await window.api.get(apiPath("/meshcore/message-window"), {
            params: { owner: snapshot.value.owner, kind, target: target(), ...options },
        });
        return sorted(data.result || []);
    }
    async function loadNewer() {
        if (loading.value || !hasNewer.value) return;
        const generation = revision,
            last = sorted(windowRows.value).at(-1);
        loading.value = true;
        try {
            const next = await fetchWindow({ after: last.id });
            if (stopped || revision !== generation || !next.length) return;
            save();
            windowRows.value = next;
            await nextTick();
            if (list.value) list.value.scrollTop = 0;
            readVisible();
        } catch {
            if (revision === generation) positionError.value = "Could not load newer messages. Please try again.";
        } finally {
            loading.value = false;
        }
    }
    watch(
        [key, visit],
        () => {
            save();
            scope = key();
            ready = false;
            revision++;
            windowRows.value = null;
            firstUnreadId.value = null;
            marked = 0;
            lastTail = null;
            positionError.value = "";
        },
        { flush: "pre" }
    );
    watch(
        () => [rows.value, snapshot.value.message_view, visit()],
        async () => {
            if (!key() || stopped || !snapshot.value.message_view || snapshot.value.message_view.target !== target())
                return;
            if (!scope) scope = key();
            const generation = revision;
            const tail = sorted(rows.value).at(-1)?.id || null;
            const appended = lastTail !== null && tail !== lastTail;
            const follow = foreground() && previousForeground;
            previousForeground = foreground();
            lastTail = tail;
            if (!ready) {
                // Capture the entry boundary before any read acknowledgement changes it.
                const view = snapshot.value.message_view;
                firstUnreadId.value = firstUnreadTarget(rows.value, view);
                let saved = null;
                try {
                    saved = JSON.parse(localStorage.getItem(scope) || "null");
                } catch {
                    /* Ignore stale bookmarks. */
                }
                const destination = firstUnreadId.value || saved?.id;
                if (destination && !rows.value.some((row) => row.id === destination)) {
                    try {
                        const page = await fetchWindow({ anchor: destination });
                        if (revision !== generation || stopped) return;
                        windowRows.value = page;
                    } catch {
                        if (revision !== generation || stopped) return;
                        if (firstUnreadId.value) {
                            positionError.value =
                                "Could not load the first unread message. Reopen this channel to try again.";
                            return;
                        }
                    }
                }
                await nextTick();
                if (revision !== generation || stopped || !list.value) return;
                const node = articles().find((item) => item.dataset.messageId === destination);
                if (node) {
                    const offset = firstUnreadId.value ? 0 : Number(saved?.offset) || 0;
                    list.value.scrollTop +=
                        node.getBoundingClientRect().top - list.value.getBoundingClientRect().top - offset;
                } else list.value.scrollTop = list.value.scrollHeight;
                positionError.value = "";
                ready = true;
                nearBottom = list.value.scrollHeight - list.value.scrollTop - list.value.clientHeight < 50;
            } else if (appended && follow && nearBottom && !windowRows.value) {
                await nextTick();
                if (revision !== generation || stopped) return;
                if (list.value) list.value.scrollTop = list.value.scrollHeight;
            }
            readVisible();
        },
        { flush: "post", immediate: true }
    );
    // Resuming must not acknowledge rows before a pending notification intent
    // has restored its destination. Polling or a scroll acknowledges visibility.
    const focus = () => {
        if (!foreground()) {
            previousForeground = false;
            save();
            clearTimeout(timer);
        }
    };
    onMounted(() => {
        window.addEventListener("focus", focus);
        window.addEventListener("blur", focus);
        document.addEventListener("visibilitychange", focus);
    });
    onBeforeUnmount(() => {
        save();
        stopped = true;
        revision++;
        clearTimeout(timer);
        window.removeEventListener("focus", focus);
        window.removeEventListener("blur", focus);
        document.removeEventListener("visibilitychange", focus);
    });
    return { visibleRows, firstUnreadId, hasNewer, loadNewer, loading, onScroll, positionError };
}
