// SPDX-License-Identifier: MIT
// Peer reports are public discovery observations, never current-state guarantees.
export function peerRadio2Rows(report) {
    const stamp = report?.observed;
    const validTime = Number.isFinite(stamp) && stamp > 0;
    const state = validTime ? report?.state : "unknown";
    const rows = [
        {
            label: "Radio2",
            value:
                state === "enabled" ? "Reported enabled" : state === "unavailable" ? "Reported unavailable" : "Unknown",
        },
    ];
    if (state === "enabled") {
        rows.push({
            label: "Radio2 profile",
            value: `${report.frequency_mhz} MHz · BW ${report.bandwidth_khz} kHz · SF${report.sf} · CR4/${report.cr} · ${report.mode === "rx" ? "receive only" : "receive/transmit"}${report.temporary ? " · temporary" : ""}`,
        });
    }
    if (validTime)
        rows.push({
            label: "Radio2 report",
            value: `${new Date(stamp * 1000).toLocaleString()} · nearby discovery · unauthenticated`,
        });
    rows.push({
        label: "Radio2 note",
        value:
            state === "unavailable"
                ? "May be off, unsupported or assigned to another protocol."
                : state === "enabled"
                  ? "Saved report; settings may have changed. Matching profiles are needed for media."
                  : "No usable profile report. Nearby discovery can check compatible repeaters; silence does not establish support.",
    });
    return rows;
}
