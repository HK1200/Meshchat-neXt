// SPDX-License-Identifier: 0BSD
// Only connection metadata is emitted to the setup guide; keys stay in the import component.
export function isBluetoothAddress(value) {
    return (
        typeof value === "string" &&
        value.length === 17 &&
        value.split(":").length === 6 &&
        value.split(":").every((part) => /^[0-9A-F]{2}$/i.test(part))
    );
}
function connection(record, config) {
    for (const value of [
        record.connection?.kind === "ble" ? record.connection.target : null,
        record.bluetooth_address,
        record.bluetoothAddress,
        config.bluetooth_address,
        config.bluetoothAddress,
    ]) {
        if (typeof value !== "string") continue;
        const address = value.replace(/^ble:\/\//i, "").toUpperCase();
        if (isBluetoothAddress(address)) return { kind: "ble", target: address };
    }
    return null;
}
function supported(config) {
    return (
        config &&
        typeof config === "object" &&
        !Array.isArray(config) &&
        (["meshchatnext-meshcore-identity-v1", "meshchatx-meshcore-identity-v1"].includes(config.format) ||
            ["private_key", "radio_settings", "contacts", "channels"].some((key) => key in config))
    );
}
export function meshcoreBackupChoices(value) {
    if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Choose a MeshCore JSON export.");
    if (!Array.isArray(value.devices))
        return [{ label: value.name || "MeshCore backup", config: value, connection: connection(value, value) }];
    if (!value.devices.length || value.devices.length > 32) throw new Error("Choose a backup containing 1–32 devices.");
    const rows = value.devices.map((record, index) => {
        if (!record || typeof record !== "object" || Array.isArray(record)) throw new Error("Invalid device record.");
        const config = record.config || record.configuration || record;
        if (!supported(config))
            throw new Error(
                "This device archive format is not supported. Export the companion configuration for each radio instead."
            );
        return {
            label: String(record.name || config.name || `Device ${index + 1}`).slice(0, 100),
            config,
            connection: connection(record, config),
        };
    });
    return rows;
}
