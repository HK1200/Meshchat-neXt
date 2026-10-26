import { apiPath } from "./constants";
export async function meshcoreNotificationRoute(key, api = window.api) {
    if (!/^meshcore-[0-9a-f]{64}$/.test(key || "")) throw new Error("Invalid MeshCore notification");
    const { data } = await api.get(apiPath("/meshcore/notification-target"), { params: { key } });
    const target = data?.result;
    if (!target || !/^[0-9a-f]{64}$/.test(target.target || "") || !/^[0-9a-f]{64}$/.test(target.owner || ""))
        throw new Error("Notification is unavailable for the selected MeshCore identity");
    if (target.kind === "tactical") {
        if (target.item && /^alert:[0-9a-f]{8}:[0-9]{1,5}$/.test(target.item)) {
            return {
                name: "map",
                query: {
                    meshcoreTeam: target.target,
                    meshcoreItem: target.item,
                    meshcoreOwner: target.owner,
                    visit: String(Date.now()),
                },
            };
        }
        if (!/^[0-9a-f]{8}:[0-9]{1,10}$/.test(target.shape || ""))
            throw new Error("Invalid MeshCore boundary notification");
        return {
            name: "map",
            query: {
                meshcoreTeam: target.target,
                meshcoreFence: target.shape,
                meshcoreOwner: target.owner,
                visit: String(Date.now()),
            },
        };
    }
    const query = { visit: String(Date.now()) };
    if (target.kind === "channel") return { name: "meshcore-channels", params: { channelId: target.target }, query };
    if (target.kind === "room") return { name: "meshcore-nodes", params: { peer: target.target }, query };
    if (target.kind === "direct") return { name: "messages", query: { ...query, meshcore: target.target } };
    throw new Error("Unsupported MeshCore notification");
}
