import { beforeEach, afterEach, it, expect, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import Book from "../../meshchatnext/src/frontend/components/sip/SipContactBook.vue";
import Link from "../../meshchatnext/src/frontend/components/sip/SipContactLink.vue";
import { sipContacts, saveSipContact, sipContactNumbers, sipContactKey } from "../../meshchatnext/src/frontend/js/sip";
let wrappers = [];
const push = vi.fn();
function mountBook() {
    const w = mount(Book, { global: { mocks: { $router: { push }, $t: (key) => key }, stubs: { Teleport: true } } });
    wrappers.push(w);
    return w;
}
beforeEach(() => {
    localStorage.clear();
    sipContacts.splice(0);
    push.mockClear();
});
afterEach(() => {
    wrappers.forEach((w) => w.unmount());
    wrappers = [];
    vi.restoreAllMocks();
});
it("preserves legacy single-number contacts and their explicit links when adding labelled numbers", () => {
    const legacy = { id: "legacy", name: "Casey", address: "1234", linked_contact: "reticulum:contact-one" };
    sipContacts.push(legacy);
    expect(sipContactNumbers(legacy)).toEqual([{ label: "Other", address: "1234" }]);
    const updated = saveSipContact({
        ...legacy,
        numbers: [
            { label: "Home", address: "1234" },
            { label: "Office", address: "5678" },
            { label: "Mobile", address: "sip:casey@example.org" },
        ],
    });
    expect(updated.id).toBe("legacy");
    expect(updated.linked_contact).toBe(legacy.linked_contact);
    expect(JSON.parse(localStorage.getItem("meshchat-next.sip.contacts.v1"))[0].numbers).toHaveLength(3);
    expect(updated.address).toBe("1234");
});
it("validates every number before saving, including non-primary header injection", () => {
    saveSipContact({ name: "Existing", address: "1234" });
    const before = localStorage.getItem("meshchat-next.sip.contacts.v1");
    expect(() =>
        saveSipContact({
            name: "Unsafe",
            numbers: [
                { label: "Home", address: "1111" },
                { label: "Office", address: "sip:x@host?Subject=bad" },
            ],
        })
    ).toThrow();
    expect(localStorage.getItem("meshchat-next.sip.contacts.v1")).toBe(before);
    expect(sipContacts).toHaveLength(1);
    expect(() => saveSipContact({ name: "Empty", numbers: [] })).toThrow();
});
it("dials each labelled number and searches secondary destinations", async () => {
    saveSipContact({
        name: "Casey",
        numbers: [
            { label: "Home", address: "1111" },
            { label: "Office", address: "2222" },
        ],
    });
    const w = mountBook();
    await w.get('[aria-label="Call Casey Office 2222"]').trigger("click");
    expect(push).toHaveBeenCalledWith({ path: "/call", query: { network: "sip", tab: "phone", sip_target: "2222" } });
    await w.get('[aria-label="Search SIP contacts"]').setValue("2222");
    expect(w.text()).toContain("Casey");
    await w.get('[aria-label="Search SIP contacts"]').setValue("absent");
    expect(w.text()).toContain("Showing 0 of 1");
    expect(w.text()).toContain("No SIP contacts match");
    await w
        .findAll("button")
        .find((b) => b.text() === "Clear SIP search")
        .trigger("click");
    expect(w.text()).toContain("Showing 1 of 1");
});
it("does not mutate saved numbers when editing is cancelled", async () => {
    const row = saveSipContact({
        name: "Casey",
        numbers: [
            { label: "Home", address: "1111" },
            { label: "Office", address: "2222" },
        ],
    });
    const w = mountBook();
    await w.get('[aria-label="Edit Casey"]').trigger("click");
    await w.get('[aria-label="Number 2 address"]').setValue("9999");
    await w
        .findAll("button")
        .find((b) => b.text() === "Cancel")
        .trigger("click");
    expect(sipContacts.find((c) => c.id === row.id).numbers[1].address).toBe("2222");
});
it("keeps the edit form and saved contacts intact if storage is full", async () => {
    saveSipContact({ name: "Casey", address: "1111" });
    const w = mountBook();
    await w.get('[aria-label="Edit Casey"]').trigger("click");
    await w.get('[aria-label="Number 1 address"]').setValue("3333");
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
        throw new Error("Storage full");
    });
    await w.find("form").trigger("submit");
    expect(w.get('[role="alert"]').text()).toContain("Storage full");
    expect(w.get('[aria-label="Number 1 address"]').element.value).toBe("3333");
    expect(sipContacts[0].address).toBe("1111");
});
it("read-only contact rows keep calls but expose no link or unlink controls", () => {
    const contact = { id: 12, remote_identity_hash: "a".repeat(32) };
    saveSipContact({
        name: "Casey",
        linked_contact: sipContactKey(contact),
        numbers: [
            { label: "Home", address: "1111" },
            { label: "Mobile", address: "2222" },
        ],
    });
    const w = mount(Link, { props: { contact, editable: false }, global: { mocks: { $router: { push } } } });
    wrappers.push(w);
    expect(w.findAll("button").map((b) => b.text())).toEqual(["Call via SIP", "Call via SIP"]);
    expect(w.find("form").exists()).toBe(false);
});
it("includes every saved SIP row without paging or truncation", () => {
    for (let i = 0; i < 24; i++)
        saveSipContact({ name: `Contact ${String(i).padStart(2, "0")}`, address: String(1000 + i) });
    const w = mountBook();
    expect(w.text()).toContain("Showing 24 of 24");
    expect(w.get('[aria-label="Edit Contact 23"]').exists()).toBe(true);
});

it("adds a SIP extension from the main contact editor into the shared telephone phonebook", async () => {
    const contact = { id: 12, name: "Casey", remote_identity_hash: "a".repeat(32) };
    const book = mountBook();
    const link = mount(Link, {
        props: { contact },
        global: { mocks: { $router: { push }, $t: (key) => key }, stubs: { Teleport: true } },
    });
    wrappers.push(link);
    await link
        .findAll("button")
        .find((b) => b.text() === "Add SIP extension")
        .trigger("click");
    await link.get('[aria-label="Number 1 type"]').setValue("Office");
    await link.get('[aria-label="Number 1 address"]').setValue("6789");
    await link.find("form").trigger("submit");
    await flushPromises();
    expect(sipContacts).toHaveLength(1);
    expect(sipContacts[0].linked_contact).toBe(sipContactKey(contact));
    expect(book.text()).toContain("Casey");
    expect(book.text()).toContain("Office · 6789");
    expect(link.text()).toContain("Office · 6789");
});
it("appends an extension to the existing linked SIP contact without losing old numbers or its ID", async () => {
    const contact = { id: 12, name: "Casey", remote_identity_hash: "a".repeat(32) };
    const old = saveSipContact({
        name: "Casey SIP",
        linked_contact: sipContactKey(contact),
        numbers: [{ label: "Home", address: "1111" }],
    });
    const link = mount(Link, {
        props: { contact },
        global: { mocks: { $router: { push }, $t: (key) => key }, stubs: { Teleport: true } },
    });
    wrappers.push(link);
    await link
        .findAll("button")
        .find((b) => b.text() === "Add SIP extension")
        .trigger("click");
    await link.get('[aria-label="Number 2 type"]').setValue("Mobile");
    await link.get('[aria-label="Number 2 address"]').setValue("2222");
    await link.find("form").trigger("submit");
    expect(sipContacts).toHaveLength(1);
    expect(sipContacts[0].id).toBe(old.id);
    expect(sipContacts[0].numbers).toEqual([
        { label: "Home", address: "1111" },
        { label: "Mobile", address: "2222" },
    ]);
});
