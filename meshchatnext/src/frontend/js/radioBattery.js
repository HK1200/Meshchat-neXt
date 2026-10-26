// Four-level indicators. MeshCore companions expose voltage rather than SOC.
export function radioBatteryLevel({ percent, voltage_mv: voltage } = {}) {
    if (typeof percent === "number" && Number.isFinite(percent) && percent >= 0 && percent <= 100)
        return Math.ceil(percent / 25);
    if (typeof voltage !== "number" || !Number.isFinite(voltage) || voltage < 2500 || voltage > 4500) return null;
    // Approximate single-cell Li-ion levels, intentionally not an exact percentage.
    if (voltage <= 3300) return 0;
    if (voltage < 3600) return 1;
    if (voltage < 3800) return 2;
    if (voltage < 4000) return 3;
    return 4;
}
