import { describe, it, expect } from "vitest";
import { roomReply, roomPostText } from "../../meshchatnext/src/frontend/js/meshcoreRoomReply";
describe("room reply context", () => {
    it("quotes author and excerpt as ordinary public room text", () => {
        const reply = roomReply({ id: "m1", text: "Meet at noon" }, { label: "Alice", prefix: "1234abcd" });
        expect(roomPostText("Yes", reply)).toBe("> Alice [1234abcd]: Meet at noon\nYes");
        expect(roomPostText("Yes", null)).toBe("Yes");
    });
    it("bounds UTF-8 context without splitting characters or allowing injected lines", () => {
        const reply = roomReply(
            { id: "m2", text: "🙂".repeat(40) },
            { label: "Alice\n\u202e" + "界".repeat(40), prefix: "invalid" }
        );
        expect(reply.header.split("\n")).toHaveLength(2);
        expect(reply.header).not.toContain("\u202e");
        expect(reply.header).not.toContain("�");
        expect(new TextEncoder().encode(reply.header).length).toBeLessThanOrEqual(61);
        expect(roomPostText("body", reply).endsWith("\nbody")).toBe(true);
    });
});
