import { appFeatures } from "./appFeatures";
import { ref, onMounted, onBeforeUnmount, watch, getCurrentInstance } from "vue";
import { apiPath, EMITTER_EVENTS } from "./constants";
import GlobalEmitter from "./GlobalEmitter";

export function meshcoreRoute(peer, radioId = null) {
    if (!/^[0-9a-f]{64}$/i.test(peer || "")) throw new Error("Invalid MeshCore public key");
    return {
        name: "messages",
        params: { destinationHash: "" },
        query: { meshcore: peer.toLowerCase(), ...(radioId ? { meshcoreRadio: radioId } : {}) },
    };
}
export function combineNetworkContacts(rns, snapshot = {}) {
    const links = new Map((snapshot.links || []).map((link) => [link.contact, link.peer]));
    const peers = new Map((snapshot.contacts || []).map((contact) => [contact.peer, contact]));
    const rows = rns.map((contact) => ({ ...contact, meshcore_key: links.get(contact.id) || null }));
    const linked = new Set(rows.map((contact) => contact.meshcore_key).filter(Boolean));
    for (const contact of peers.values()) {
        if (!linked.has(contact.peer))
            rows.push({
                id: `meshcore:${contact.peer}`,
                name: contact.name || contact.peer.slice(0, 12),
                meshcore_key: contact.peer,
                meshcore_only: true,
            });
    }
    return rows;
}
export function useMeshCoreUi(peer = () => null, enabled = () => true, channel = () => null, visit = () => "") {
    const snapshot = ref({
        available: false,
        connected: false,
        contacts: [],
        links: [],
        conversations: [],
        messages: [],
        channels: [],
        nodes: [],
        channel_banishments: [],
        channel_messages: [],
    });
    const instance = getCurrentInstance();
    const radio = () => instance?.proxy?.$route?.query?.meshcoreRadio || null;
    const error = ref("");
    const lifetime = new AbortController();
    const lease = {};
    const channelsChanged = (sender) => {
        if (sender !== lease) refresh();
    };
    let timer,
        fetching = false,
        refreshAgain = false,
        stopped = false,
        generation = 0;
    async function refresh() {
        if (stopped || !appFeatures.meshcore || !enabled()) return;
        if (fetching) {
            refreshAgain = true;
            return;
        }
        fetching = true;
        const current = ++generation;
        const key = peer(),
            channelKey = channel(),
            entry = visit(),
            radioId = radio();
        try {
            const { data } = await window.api.get(apiPath("/meshcore/ui"), {
                signal: lifetime.signal,
                params: {
                    ...(radioId ? { radio: radioId } : {}),
                    ...(key ? { peer: key } : {}),
                    ...(channelKey ? { channel_id: channelKey } : {}),
                },
            });
            if (
                !stopped &&
                current === generation &&
                key === peer() &&
                channelKey === channel() &&
                entry === visit() &&
                radioId === radio()
            ) {
                if (!data?.result || !Array.isArray(data.result.contacts)) return;
                snapshot.value = { ...snapshot.value, active_notification_key: null, ...data.result };
                error.value = "";
            }
        } catch (e) {
            if (!stopped && current === generation) {
                if (e?.response?.status === 503)
                    snapshot.value = {
                        ...snapshot.value,
                        available: false,
                        connected: false,
                        active_notification_key: null,
                    };
                else error.value = "MeshCore could not refresh. Try again.";
            }
        } finally {
            fetching = false;
            if (refreshAgain && !stopped) {
                refreshAgain = false;
                queueMicrotask(refresh);
            }
        }
    }
    async function action(name, body) {
        const guarded = [
            "message",
            "contact-add",
            "channel-add",
            "channel-message",
            "channel-read",
            "channel-order",
            "channel-mute",
            "channel-banish",
            "channel-unbanish",
            "node-login",
            "node-logout",
            "node-status",
            "node-admin",
            "room-message",
            "announce",
            "channel-scope",
            "channel-remove",
            "channel-visibility",
            "tool-radio-stats",
            "tool-rx-log",
            "tool-trace",
            "regions-scan",
            "regions-auto",
            "regions-read",
            "regions-add",
            "regions-default",
            "regions-discover",
            "node-discover",
            "node-save",
            "node-remove",
        ].includes(name)
            ? { ...body, expected_owner: snapshot.value.owner }
            : body;
        const radioId = radio() || snapshot.value.radio_id;
        const result = radioId
            ? await window.api.post(apiPath(`/meshcore/${name}`), guarded, { params: { radio: radioId } })
            : await window.api.post(apiPath(`/meshcore/${name}`), guarded);
        if (name === "radio-configure" && body.active && radio())
            await instance.proxy.$router.replace({
                query: { ...instance.proxy.$route.query, meshcoreRadio: body.active },
            });
        if (name === "radio-remove" && body.radio_id === radio())
            await instance.proxy.$router.replace({
                query: { ...instance.proxy.$route.query, meshcoreRadio: undefined },
            });
        await refresh();
        if (name.startsWith("radio-")) GlobalEmitter.emit("meshcore.radios-changed", lease);
        if (["channel-order", "channel-visibility", "channel-remove"].includes(name))
            GlobalEmitter.emit("meshcore.channels-changed", lease);
        return result.data.result;
    }
    function identityChanged() {
        ++generation;
        snapshot.value = { ...snapshot.value, links: [], account: null };
        refresh();
    }
    onMounted(() => {
        GlobalEmitter.on(EMITTER_EVENTS.IDENTITY_SWITCHED, identityChanged);
        GlobalEmitter.on("meshcore.channels-changed", channelsChanged);
        GlobalEmitter.on("meshcore.radios-changed", channelsChanged);
        if (enabled()) {
            refresh();
            timer = setInterval(refresh, 4000);
        }
    });
    watch(enabled, (value) => {
        clearInterval(timer);
        if (value && !stopped) {
            refresh();
            timer = setInterval(refresh, 4000);
        }
    });
    onBeforeUnmount(() => {
        stopped = true;
        lifetime.abort();
        GlobalEmitter.off(EMITTER_EVENTS.IDENTITY_SWITCHED, identityChanged);
        GlobalEmitter.off("meshcore.channels-changed", channelsChanged);
        GlobalEmitter.off("meshcore.radios-changed", channelsChanged);
        ++generation;
        clearInterval(timer);
    });
    watch(
        () => [peer(), channel(), visit(), radio()],
        () => {
            snapshot.value = {
                ...snapshot.value,
                messages: [],
                channel_messages: [],
                message_view: null,
                active_notification_key: null,
            };
            refresh();
        }
    );
    return { snapshot, error, refresh, action };
}

export function meshcoreChannelRoute(channel, radioId = null) {
    if (!/^[0-9a-f]{64}$/i.test(channel || "")) throw new Error("Invalid MeshCore channel");
    return {
        name: "meshcore-channels",
        params: { channelId: channel },
        ...(radioId ? { query: { meshcoreRadio: radioId } } : {}),
    };
}
export function meshcoreNodeRoute(peer, radioId = null) {
    if (!/^[0-9a-f]{64}$/i.test(peer || "")) throw new Error("Invalid MeshCore node");
    return { name: "meshcore-nodes", params: { peer }, ...(radioId ? { query: { meshcoreRadio: radioId } } : {}) };
}
export function meshcoreNavAnchor(items) {
    return (
        items.find((item) => item.id === "relay-chat")?.id ||
        items.find((item) => item.id === "contacts")?.id ||
        items[0]?.id
    );
}
