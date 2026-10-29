import { afterEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import Feature from "ol/Feature";
import Point from "ol/geom/Point";
import LineString from "ol/geom/LineString";
import { fromLonLat } from "ol/proj";
import { mapNodeDetails, pickMapNodeDetails } from "@/components/map/internal/mapNodeDetails";
import { bindMapNodeLongPress } from "@/components/map/internal/mapNodeLongPress";
import MapNodeDetailsPopup from "@/components/map/internal/MapNodeDetailsPopup.vue";
const point = (props = {}) => new Feature({ geometry: new Point(fromLonLat([-122, 49])), ...props });
const rows = (x) => Object.fromEntries(x.rows.map((r) => [r.label, r.value]));
afterEach(() => vi.useRealTimers());

describe("information for every visible map dot", () => {
    it("shows Reticulum public identity, reported position and telemetry without serializing secrets", () => {
        const result = mapNodeDetails(
            point({
                telemetry: {
                    destination_hash: "a1".repeat(16),
                    timestamp: 1700000000,
                    telemetry: {
                        location: { latitude: 49, longitude: -122, altitude: 0, speed: 0 },
                        battery: { charge_percent: 0 },
                    },
                    private_key: "NEVER SHOW",
                },
                peer: { display_name: "Reticulum peer" },
            })
        );
        expect(result.title).toBe("Reticulum peer");
        expect(result.source).toBe("Reticulum");
        expect(rows(result)).toMatchObject({
            "Public address": "a1".repeat(16),
            Position: "49.000000, -122.000000",
            Altitude: "0 m",
            Speed: "0 m/s",
            Battery: "0%",
        });
        expect(JSON.stringify(result)).not.toContain("NEVER SHOW");
    });
    it("shows MeshCore type, radio and freshness without inventing missing values", () => {
        const result = mapNodeDetails(
            point({
                meshcore: {
                    name: "Repeater",
                    kind: 2,
                    public_key: "b2".repeat(32),
                    latitude: 49,
                    longitude: -122,
                    heard: 1700000000,
                },
                meshcoreMapContext: { radio_id: "radio-one" },
            })
        );
        expect(result.source).toBe("MeshCore");
        expect(rows(result)).toMatchObject({ Type: "Repeater", Radio: "radio-one" });
        expect(rows(result)["Last heard"]).toBeTruthy();
        expect(rows(result)).not.toHaveProperty("Battery");
        expect(rows(result).Radio2).toBe("Unknown");
    });
    it("adds team callsign, role and report context only for team records", () => {
        const context = { team_enabled: true, roles: ["Medic"], urgencies: ["Routine"] };
        const team = mapNodeDetails(
            point({
                meshcoreTeam: {
                    kind: "report",
                    callsign: "Team one",
                    alias: "001122",
                    role: 0,
                    urgency: 0,
                    activity: "Observation",
                    note: "Known information",
                },
                meshcoreMapContext: context,
            })
        );
        expect(team.team).toBe(true);
        expect(rows(team)).toMatchObject({
            Callsign: "Team one",
            Role: "Medic",
            Priority: "Routine",
            View: "Teams",
            Activity: "Observation",
        });
        const normal = mapNodeDetails(
            point({ meshcore: { name: "Client", role: 0, callsign: "Not a team record" }, meshcoreMapContext: context })
        );
        expect(rows(normal)).not.toHaveProperty("Role");
        expect(rows(normal)).not.toHaveProperty("Callsign");
    });
    it("provides coordinates for unnamed points and discovered interfaces", () => {
        const generic = mapNodeDetails(point());
        expect(generic.title).toBe("Unnamed map point");
        expect(rows(generic).Position).toBe("49.000000, -122.000000");
        const found = mapNodeDetails(
            point({ discovered: { name: "Nearby interface", latitude: 0, longitude: 0, type: "TCP" } })
        );
        expect(found.source).toBe("Discovered interface");
        expect(rows(found).Position).toBe("0.000000, 0.000000");
    });
    it("gives captured-route dots identity context without claiming confirmed relay traffic", () => {
        const result = mapNodeDetails(
            point({ meshcoreRouteNode: { name: "Path node", order: 0, public_key: "c3".repeat(32) } })
        );
        expect(rows(result)["Captured path position"]).toBe("1");
        expect(rows(result)["Path context"]).toContain("does not prove");
    });
    it("offers all overlapping and clustered nodes while ignoring line geometry", () => {
        const a = point({ name: "One" }),
            b = point({ name: "Two" });
        const cluster = point({ clusterItems: [a, b] });
        const map = {
            getEventPixel: () => [10, 10],
            getCoordinateFromPixel: () => fromLonLat([-122, 49]),
            forEachFeatureAtPixel: (_, cb) =>
                [
                    cluster,
                    a,
                    new Feature(
                        new LineString([
                            [0, 0],
                            [1, 1],
                        ])
                    ),
                ].forEach(cb),
        };
        expect(pickMapNodeDetails(map, {}).map((x) => x.title)).toEqual(["One", "Two"]);
    });
});

describe("stationary long-press gestures", () => {
    const event = (type, options = {}) => {
        const e = new MouseEvent(type, { bubbles: true, button: 0, clientX: 20, clientY: 20, ...options });
        Object.defineProperty(e, "pointerId", { value: options.pointerId ?? 1 });
        if (options.isPrimary === false) Object.defineProperty(e, "isPrimary", { value: false });
        return e;
    };
    function setup() {
        vi.useFakeTimers();
        const element = document.createElement("div"),
            open = vi.fn(),
            finish = vi.fn();
        const binding = bindMapNodeLongPress(element, { pick: () => [{ title: "Node" }], open, finish });
        return { element, open, finish, binding };
    }
    it("opens once for a hold and finishes only at release, even for a very long hold", () => {
        const { element, open, finish, binding } = setup();
        element.dispatchEvent(event("pointerdown"));
        vi.advanceTimersByTime(550);
        expect(open).toHaveBeenCalledTimes(1);
        vi.advanceTimersByTime(3000);
        expect(finish).not.toHaveBeenCalled();
        element.dispatchEvent(event("pointerup"));
        expect(finish).toHaveBeenCalledTimes(1);
        binding.dispose();
    });
    it.each(["drag", "second finger", "cancel", "release", "dispose"])("does not open after %s", (action) => {
        const { element, open, binding } = setup();
        element.dispatchEvent(event("pointerdown"));
        if (action === "drag") element.dispatchEvent(event("pointermove", { clientX: 50 }));
        if (action === "second finger") element.dispatchEvent(event("pointerdown", { pointerId: 2, isPrimary: false }));
        if (action === "cancel") element.dispatchEvent(event("pointercancel"));
        if (action === "release") element.dispatchEvent(event("pointerup"));
        if (action === "dispose") binding.dispose();
        vi.advanceTimersByTime(1000);
        expect(open).not.toHaveBeenCalled();
        binding.dispose();
    });
    it("finishes a hold when the pointer is released over the popup outside the canvas", () => {
        const { element, open, finish, binding } = setup();
        element.dispatchEvent(event("pointerdown"));
        vi.advanceTimersByTime(550);
        expect(open).toHaveBeenCalledTimes(1);
        window.dispatchEvent(event("pointerup"));
        expect(finish).toHaveBeenCalledTimes(1);
        element.dispatchEvent(event("pointerdown"));
        vi.advanceTimersByTime(550);
        expect(open).toHaveBeenCalledTimes(2);
        binding.dispose();
    });
    it("cancels a pending hold when the window loses focus", () => {
        const { element, open, binding } = setup();
        element.dispatchEvent(event("pointerdown"));
        window.dispatchEvent(new Event("blur"));
        vi.advanceTimersByTime(1000);
        expect(open).not.toHaveBeenCalled();
        binding.dispose();
    });
    it("does not intercept buttons or empty map space", () => {
        const { element, open, binding } = setup();
        const button = document.createElement("button");
        element.append(button);
        button.dispatchEvent(event("pointerdown"));
        vi.advanceTimersByTime(1000);
        expect(open).not.toHaveBeenCalled();
        binding.dispose();
        const blank = bindMapNodeLongPress(element, { pick: () => [], open });
        element.dispatchEvent(event("pointerdown"));
        vi.advanceTimersByTime(1000);
        expect(open).not.toHaveBeenCalled();
        blank.dispose();
    });
});

it("renders reported text safely, switches overlapping nodes, and closes on Back", async () => {
    const wrapper = mount(MapNodeDetailsPopup, {
        props: {
            items: [
                {
                    title: "<img src=x onerror=alert(1)>",
                    source: "MeshCore",
                    rows: [{ label: "Note", value: "<script>not executable</script>" }],
                },
                { title: "Second", source: "Reticulum", rows: [{ label: "Position", value: "49, -122" }] },
            ],
        },
    });
    expect(wrapper.find("img").exists()).toBe(false);
    expect(wrapper.find("script").exists()).toBe(false);
    expect(wrapper.text()).toContain("<script>not executable</script>");
    await wrapper.find("select").setValue("1");
    expect(wrapper.find("h3").text()).toBe("Second");
    await wrapper.trigger("app-back");
    expect(wrapper.emitted("close")).toHaveLength(1);
    wrapper.unmount();
});
