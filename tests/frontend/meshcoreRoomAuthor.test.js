import { describe, it, expect } from "vitest";
import { roomAuthor } from "../../meshchatnext/src/frontend/js/meshcoreRoomAuthor";
const key = "abcd1234" + "11".repeat(28);
describe("Room author contact hints", () => {
    it("uses a unique saved name with its unverified prefix", () => {
        expect(roomAuthor("ABCD1234", [{ peer: key.toUpperCase(), name: "Alice", active: true }])).toEqual({
            label: "Alice",
            prefix: "abcd1234",
            matched: true,
        });
    });
    it("does not guess between distinct contacts sharing four bytes, even if their names agree", () => {
        expect(
            roomAuthor("abcd1234", [
                { peer: key, name: "Alice" },
                { peer: "abcd1234" + "22".repeat(28), name: "Alice" },
            ])
        ).toEqual({ label: "Author abcd1234", prefix: "abcd1234", matched: false });
    });
    it("ignores inactive, malformed and unrelated contacts", () => {
        expect(
            roomAuthor("abcd1234", [
                { peer: key, name: "Inactive", active: false },
                { peer: "abcd1234" + "22".repeat(28), name: "Removed", active: 0 },
                { peer: "abcd1234", name: "Truncated" },
                { peer: "ff".repeat(32), name: "Elsewhere" },
            ]).matched
        ).toBe(false);
    });
    it("deduplicates full keys and falls back for an unnamed contact", () => {
        expect(
            roomAuthor("abcd1234", [
                { peer: key, name: "Alice" },
                { peer: key, name: "Alice" },
            ]).label
        ).toBe("Alice");
        expect(roomAuthor("abcd1234", [{ peer: key, name: " " }]).label).toBe("Author abcd1234");
    });
    it.each([undefined, null, 12345678, "abcd", "xxxxxxxx", "abcd12345"])(
        "rejects malformed room author %s",
        (signature) => {
            expect(roomAuthor(signature, [{ peer: key, name: "Alice" }]).label).toBe("Unknown author");
        }
    );
});
