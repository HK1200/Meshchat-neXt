// SPDX-License-Identifier: 0BSD
// Format references: ATAK-CIV MissionPackageManifest / MissionPackageContent.
// Independent point-only interchange; no external connections or radio operations.
import JSZip from "jszip";
import { cotShape, cotShapeDetail } from "./meshcoreCotGeometry";
const LIMIT = 1024 * 1024;
const MAX_ITEMS = 100;
export const TAK_PACKAGE_LIMIT = 10 * LIMIT;
const FILE_LIMIT = 5 * LIMIT;
const xml = (value) =>
    String(value ?? "").replace(
        /[<>&"']/g,
        (c) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", '"': "&quot;", "'": "&apos;" })[c]
    );
function parse(text) {
    if (new TextEncoder().encode(text).length > LIMIT || /<!DOCTYPE|<!ENTITY/i.test(text))
        throw new Error("Unsupported or oversized XML.");
    const doc = new DOMParser().parseFromString(text, "application/xml");
    if (doc.querySelector("parsererror")) throw new Error("Invalid XML.");
    return doc;
}
export function readCot(text) {
    const doc = parse(text);
    const events =
        doc.documentElement.tagName === "event" ? [doc.documentElement] : [...doc.querySelectorAll("events > event")];
    if (!events.length || events.length > MAX_ITEMS) throw new Error("Choose a CoT file containing 1–100 map events.");
    return events.map((event) => {
        const point = [...event.children].find((n) => n.tagName === "point");
        const latitude = Number(point?.getAttribute("lat")),
            longitude = Number(point?.getAttribute("lon"));
        if (
            !point ||
            !point.hasAttribute("lat") ||
            !point.hasAttribute("lon") ||
            !point.getAttribute("lat").trim() ||
            !point.getAttribute("lon").trim() ||
            !Number.isFinite(latitude) ||
            Math.abs(latitude) > 90 ||
            !Number.isFinite(longitude) ||
            Math.abs(longitude) > 180
        )
            throw new Error("CoT event has invalid coordinates.");
        const label =
            event.querySelector("detail > contact")?.getAttribute("callsign") ||
            event.getAttribute("uid") ||
            "Imported point";
        const note = event.querySelector("detail > remarks")?.textContent || "";
        const shape = cotShape(event);
        return {
            kind: "pin",
            latitude,
            longitude,
            pin_kind: 0,
            label: truncate(label, shape ? 24 : 32),
            note: truncate(note, 60),
            sourceUid: event.getAttribute("uid") || "",
            sourceType: event.getAttribute("type") || "",
            stale: event.getAttribute("stale") || "",
            ...shape,
        };
    });
}
function truncate(value, bytes) {
    let result = "";
    for (const character of value) {
        if (new TextEncoder().encode(result + character).length > bytes) break;
        result += character;
    }
    return result;
}
export function cotPoint(item, uid = crypto.randomUUID(), now = Date.now()) {
    const shape = item.kind === "shape" ? cotShapeDetail(item, xml) : null;
    const latitude = shape?.latitude ?? item.latitude,
        longitude = shape?.longitude ?? item.longitude;
    if (
        !Number.isFinite(latitude) ||
        Math.abs(latitude) > 90 ||
        !Number.isFinite(longitude) ||
        Math.abs(longitude) > 180
    )
        throw new Error("Item has invalid coordinates.");
    const time = new Date(now).toISOString(),
        stale = new Date(now + 300000).toISOString();
    // Export as a generic unknown point: short MeshCore aliases do not establish affiliation.
    return `<event version="2.0" uid="${xml(uid)}" type="${shape?.type || "a-u-G"}" time="${time}" start="${time}" stale="${stale}" how="h-e"><point lat="${latitude}" lon="${longitude}" hae="9999999" ce="9999999" le="9999999"/><detail><contact callsign="${xml(item.label || item.callsign || "MeshCore point")}"/><remarks>${xml(item.note || item.place || "")}</remarks>${shape?.detail || ""}</detail></event>`;
}
export async function writeTakPackage(items, options = {}) {
    if ((!items.length && !options.files?.length) || items.length > MAX_ITEMS)
        throw new Error("Select 1–100 map items.");
    const zip = new JSZip(),
        uid = crypto.randomUUID();
    const ids = new Map();
    const contents = items
        .map((item) => {
            const id = crypto.randomUUID(),
                path = `${id}/${id}.cot`;
            ids.set(item.sourceUid || item.source_uid || String(ids.size), id);
            zip.file(path, cotPoint(item, id));
            return `<Content zipEntry="${path}" ignore="false"><Parameter name="uid" value="${id}"/><Parameter name="isCoT" value="true"/></Content>`;
        })
        .join("");
    const files = options.files || [];
    if (files.length > 100) throw new Error("Too many package files.");
    let total = 0;
    const fileContents = files
        .map((file) => {
            if (!(file.bytes instanceof Uint8Array) || file.bytes.length > FILE_LIMIT)
                throw new Error("Each package file must be at most 5 MB.");
            total += file.bytes.length;
            if (total > 20 * LIMIT) throw new Error("Package files exceed 20 MB.");
            const name = String(file.name || "attachment.bin")
                .split(/[\\/]/)
                .at(-1)
                // eslint-disable-next-line no-control-regex -- Remove control characters from untrusted filenames.
                .replace(/[\x00-\x1f:*?"<>|]/g, "_")
                .slice(0, 120);
            const path = `${crypto.randomUUID()}/${name || "attachment.bin"}`;
            zip.file(path, file.bytes);
            const owner = ids.get(file.uid);
            return `<Content zipEntry="${xml(path)}" ignore="false"><Parameter name="name" value="${xml(name)}"/>${owner ? `<Parameter name="uid" value="${xml(owner)}"/>` : ""}</Content>`;
        })
        .join("");
    zip.file(
        "MANIFEST/manifest.xml",
        `<MissionPackageManifest version="2"><Configuration><Parameter name="uid" value="${uid}"/><Parameter name="name" value="MeshCore map items"/></Configuration><Contents>${contents}${fileContents}</Contents></MissionPackageManifest>`
    );
    // STORE keeps packages predictable and locally inspectable; no media or channel keys.
    const bytes = await zip.generateAsync({ type: "uint8array", compression: "STORE" });
    if (bytes.length > TAK_PACKAGE_LIMIT) throw new Error("Package exceeds 10 MB. Export fewer items or attachments.");
    return bytes;
}
async function boundedBytes(entry, budget, limit = LIMIT) {
    return new Promise((resolve, reject) => {
        const chunks = [];
        let size = 0;
        const stream = entry.internalStream("uint8array");
        stream
            .on("data", (chunk) => {
                size += chunk.length;
                budget.remaining -= chunk.length;
                if (size > limit || budget.remaining < 0) {
                    stream.pause();
                    reject(new Error("Package entry is too large."));
                    return;
                }
                chunks.push(chunk);
            })
            .on("error", reject)
            .on("end", () => {
                const data = new Uint8Array(size);
                let offset = 0;
                for (const chunk of chunks) {
                    data.set(chunk, offset);
                    offset += chunk.length;
                }
                resolve(data);
            })
            .resume();
    });
}
async function boundedText(entry, budget) {
    return new TextDecoder("utf-8", { fatal: true }).decode(await boundedBytes(entry, budget));
}
export function checkTakZip(bytes) {
    const raw = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
    if (raw.length > TAK_PACKAGE_LIMIT || raw.length < 22) throw new Error("Invalid or oversized ZIP package.");
    const view = new DataView(raw.buffer, raw.byteOffset, raw.byteLength);
    let end = -1;
    for (let p = raw.length - 22; p >= Math.max(0, raw.length - 65557); p--)
        if (view.getUint32(p, true) === 0x06054b50 && p + 22 + view.getUint16(p + 20, true) === raw.length) {
            end = p;
            break;
        }
    if (end < 0 || view.getUint16(end + 4, true) || view.getUint16(end + 6, true))
        throw new Error("Unsupported ZIP package.");
    const count = view.getUint16(end + 10, true),
        size = view.getUint32(end + 12, true),
        start = view.getUint32(end + 16, true);
    if (count > 512 || view.getUint16(end + 8, true) !== count || start + size > end)
        throw new Error("Invalid ZIP directory.");
    let offset = start,
        actual = 0,
        expanded = 0;
    while (offset < start + size) {
        if (offset + 46 > end || view.getUint32(offset, true) !== 0x02014b50) throw new Error("Invalid ZIP entry.");
        const length = view.getUint16(offset + 28, true),
            extra = view.getUint16(offset + 30, true),
            comment = view.getUint16(offset + 32, true);
        const bytes = view.getUint32(offset + 24, true);
        expanded += bytes;
        actual++;
        if (actual > 512 || bytes > FILE_LIMIT || expanded > 20 * LIMIT || view.getUint16(offset + 8, true) & 1)
            throw new Error("Package entry is too large or encrypted.");
        offset += 46 + length + extra + comment;
        if (offset > start + size) throw new Error("Invalid ZIP entry length.");
    }
    if (actual !== count || offset !== start + size) throw new Error("ZIP entry count mismatch.");
}
export async function readTakPackage(bytes) {
    if (bytes.byteLength > TAK_PACKAGE_LIMIT) throw new Error("Choose a package smaller than 10 MB.");
    checkTakZip(bytes);
    const budget = { remaining: 20 * LIMIT };
    const zip = await JSZip.loadAsync(bytes, { createFolders: false });
    const entries = Object.values(zip.files);
    if (entries.length > 512) throw new Error("Too many package entries.");
    for (const entry of entries) {
        const name = entry.unsafeOriginalName || entry.name;
        if (name.startsWith("/") || name.includes("\\") || name.split("/").includes(".."))
            throw new Error("Unsafe package path.");
    }
    const manifest = zip.file("MANIFEST/manifest.xml");
    if (!manifest) throw new Error("No TAK package manifest found.");
    const doc = parse(await boundedText(manifest, budget));
    if (doc.documentElement.tagName !== "MissionPackageManifest") throw new Error("Invalid package manifest.");
    const content = [...doc.querySelectorAll("Contents > Content")];
    if (content.length > MAX_ITEMS * 2) throw new Error("Too many package contents.");
    const items = [],
        files = [],
        skipped = [];
    const seen = new Set();
    for (const item of content) {
        const path = item.getAttribute("zipEntry");
        if (item.getAttribute("ignore") === "true") continue;
        if (!path) throw new Error("Package content has no path.");
        if (seen.has(path)) throw new Error("Duplicate package reference.");
        seen.add(path);
        const file = zip.file(path);
        if (!file) throw new Error("Package references a missing event.");
        if (!path.toLowerCase().endsWith(".cot")) {
            const uid =
                [...item.querySelectorAll("Parameter")]
                    .find((node) => node.getAttribute("name") === "uid")
                    ?.getAttribute("value") || "";
            if (files.length >= 100) throw new Error("Too many package files.");
            files.push({
                name: path.split("/").at(-1),
                path,
                uid,
                bytes: await boundedBytes(file, budget, FILE_LIMIT),
            });
            continue;
        }
        const points = readCot(await boundedText(file, budget));
        items.push(...points);
        if (items.length > MAX_ITEMS) throw new Error("Too many map events.");
    }
    if (!items.length && !files.length) throw new Error("No supported contents in package.");
    return { items, files, skipped: skipped.length };
}
