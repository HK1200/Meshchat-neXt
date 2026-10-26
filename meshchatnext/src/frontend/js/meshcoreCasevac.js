// SPDX-License-Identifier: MIT
// Wire labels follow the pinned Open TAK CASEVAC nine-line schema.
export const precedence = [
    ["urgent", "Urgent"],
    ["urgent_surgical", "Urgent surgical"],
    ["priority", "Priority"],
    ["routine", "Routine"],
    ["convenience", "Convenience"],
];
export const nationality = [
    ["us_military", "US military"],
    ["us_civilian", "US civilian"],
    ["non_us_military", "Non-US military"],
    ["non_us_civilian", "Non-US civilian"],
    ["epw", "Prisoner of war"],
    ["child", "Child"],
];
export const equipment = ["None", "Hoist", "Extraction equipment", "Ventilator", "Other"];
export const security = [
    "No enemy troops",
    "Possible enemy",
    "Enemy in area, approach with caution",
    "Armed escort required",
];
export const marking = ["Panels", "Pyrotechnic", "Smoke", "None", "Other"];
export const terrain = ["Flat / none", "Slope", "Rough", "Loose debris", "Other"];
export const nbc = ["None", "Nuclear", "Biological", "Chemical"];
export const countFields = [...precedence, ...nationality, ["litter", "Litter"], ["ambulatory", "Ambulatory"]];
export function casevacLines(record) {
    const counts = (list) =>
        list
            .filter(([key]) => record[key])
            .map(([key, label]) => `${label}: ${record[key]}`)
            .join(", ") || "Unspecified";
    const flags = (names, value) => names.filter((_, i) => (value || 0) & (1 << i)).join(", ") || "None";
    return [
        `1 · ${record.latitude?.toFixed(5)}, ${record.longitude?.toFixed(5)} ${record.place || ""}`,
        `2 · ${record.frequency || "Frequency unspecified"} / ${record.callsign || "Callsign unspecified"}`,
        `3 · ${counts(precedence)}`,
        `4 · ${flags(equipment, record.equipment_flags)}`,
        `5 · Litter: ${record.litter || 0}, ambulatory: ${record.ambulatory || 0}`,
        `6 · ${security[record.security] || "Unspecified"}`,
        `7 · ${marking[record.marking] || "Unspecified"} ${record.marking_detail || ""}`,
        `8 · ${counts(nationality)}`,
        `9 · ${flags(terrain, record.terrain_flags)} / NBC: ${nbc[record.nbc] || "None"}`,
    ];
}
