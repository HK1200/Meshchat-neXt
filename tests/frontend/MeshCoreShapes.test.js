import { describe, it, expect } from "vitest";
import Feature from "ol/Feature";
import LineString from "ol/geom/LineString";
import Polygon from "ol/geom/Polygon";
import Circle from "ol/geom/Circle";
import { fromLonLat, toLonLat } from "ol/proj";
import { drawingShape, shapeGeometry } from "../../meshchatnext/src/frontend/js/meshcoreShapes";
describe("MeshCore drawing copies", () => {
    it("shares line coordinates as latitude/longitude without changing the original geometry", () => {
        const coordinates = [
            [2, 1],
            [2.001, 1.001],
        ].map((p) => fromLonLat(p));
        const feature = new Feature(new LineString(coordinates));
        const before = JSON.stringify(feature.getGeometry().getCoordinates());
        const item = drawingShape(feature, true);
        expect(item.shape_kind).toBe(5);
        expect(item.points[0][0]).toBeCloseTo(1);
        expect(item.points[0][1]).toBeCloseTo(2);
        expect(JSON.stringify(feature.getGeometry().getCoordinates())).toBe(before);
        expect(toLonLat(shapeGeometry(item).getCoordinates()[1])[0]).toBeCloseTo(2.001);
    });
    it("removes only a repeated closing vertex and rejects polygon holes", () => {
        const points = [
            [0, 0],
            [1, 0],
            [1, 1],
            [0, 0],
        ].map((p) => fromLonLat(p));
        const feature = new Feature(new Polygon([points]));
        const item = drawingShape(feature);
        expect(item.points).toHaveLength(3);
        expect(shapeGeometry(item).getCoordinates()[0]).toHaveLength(4);
        feature.getGeometry().setCoordinates([points, points]);
        expect(() => drawingShape(feature)).toThrow("holes");
    });
    it("converts projected circles to a metre radius and validates received shapes", () => {
        const item = drawingShape(new Feature(new Circle(fromLonLat([0, 0]), 100)));
        expect(item.radius_m).toBeGreaterThan(98);
        expect(item.radius_m).toBeLessThan(102);
        expect(shapeGeometry(item).getType()).toBe("Polygon");
        expect(shapeGeometry({ ...item, points: [[100, 0]] })).toBeNull();
        expect(shapeGeometry({ ...item, radius_m: NaN })).toBeNull();
        expect(() =>
            drawingShape(
                new Feature(
                    new LineString([
                        [NaN, 1],
                        [2, 3],
                    ])
                )
            )
        ).toThrow("invalid");
    });
});
