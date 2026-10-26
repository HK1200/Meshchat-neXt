package com.meshchatnext.meshcore;

import android.Manifest;
import android.annotation.SuppressLint;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothManager;
import android.bluetooth.le.*;
import android.content.Context;
import android.os.Build;
import android.os.ParcelUuid;
import java.util.Collections;

/** Service-filtered discovery. stopScan uses only this session's callback. */
@SuppressLint("MissingPermission")
public final class BleDiscovery extends NativeSession {
    private final Context context;
    private BluetoothLeScanner scanner;
    private boolean started;

    public BleDiscovery(Context context) { this.context = context.getApplicationContext(); }

    private final ScanCallback callback = new ScanCallback() {
        @Override public void onScanResult(int callbackType, ScanResult result) {
            if (closed) return;
            try {
                String name = result.getScanRecord() == null ? null : result.getScanRecord().getDeviceName();
                emit("found", (name == null ? "" : name).getBytes(java.nio.charset.StandardCharsets.UTF_8),
                    result.getDevice().getAddress());
            }
            catch (SecurityException error) { emit("error", null, "bluetooth_permission_required"); close(); }
        }
        @Override public void onScanFailed(int code) {
            if (!closed) { emit("error", null, "ble_scan_failed"); close(); }
        }
    };

    @Override public synchronized void start() {
        if (started || closed) throw new IllegalStateException("Session is single use");
        started = true;
        try {
            if (Build.VERSION.SDK_INT >= 31) {
                BleSession.requirePermission(context, Manifest.permission.BLUETOOTH_SCAN);
                BleSession.requirePermission(context, Manifest.permission.BLUETOOTH_CONNECT);
            } else {
                BleSession.requirePermission(context, Manifest.permission.ACCESS_FINE_LOCATION);
            }
            BluetoothManager manager = (BluetoothManager) context.getSystemService(Context.BLUETOOTH_SERVICE);
            BluetoothAdapter adapter = manager == null ? null : manager.getAdapter();
            scanner = adapter == null ? null : adapter.getBluetoothLeScanner();
            if (scanner == null) throw new IllegalStateException("Bluetooth disabled");
            ScanFilter filter = new ScanFilter.Builder().setServiceUuid(new ParcelUuid(BleSession.SERVICE)).build();
            scanner.startScan(Collections.singletonList(filter), new ScanSettings.Builder()
                .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY).build(), callback);
        } catch (SecurityException error) { emit("error", null, "bluetooth_permission_required"); close(); }
        catch (Exception error) { emit("error", null, "ble_scan_unavailable"); close(); }
    }

    @Override public void send(byte[] data) { throw new UnsupportedOperationException("Discovery only"); }

    @Override public synchronized void close() {
        if (closed) return;
        closed = true;
        if (scanner != null) {
            try { scanner.stopScan(callback); } catch (Exception ignored) {}
            scanner = null;
        }
        emit("closed", null, "scan_closed");
    }
}
