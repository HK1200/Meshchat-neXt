package com.meshchatnext.meshcore;

import android.Manifest;
import android.annotation.SuppressLint;
import android.bluetooth.*;
import android.content.Context;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Handler;
import android.os.HandlerThread;
import com.meshchatnext.radio.DeviceAccess;
import java.util.UUID;

/** One GATT client per session. Never touches org.able's RNode GATT client or adapter state. */
@SuppressLint("MissingPermission")
public final class BleSession extends NativeSession {
    static final UUID SERVICE = UUID.fromString("6e400001-b5a3-f393-e0a9-e50e24dcca9e");
    private static final UUID RX = UUID.fromString("6e400002-b5a3-f393-e0a9-e50e24dcca9e");
    private static final UUID TX = UUID.fromString("6e400003-b5a3-f393-e0a9-e50e24dcca9e");
    private static final UUID CCCD = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb");
    private final Context context;
    private final String address;
    private final HandlerThread thread = new HandlerThread("meshcore-ble");
    private Handler handler;
    private BluetoothGatt gatt;
    private BluetoothGattCharacteristic rx;
    private BluetoothGattCharacteristic tx;
    private BluetoothGattDescriptor cccd;
    private int mtu = 23;
    private boolean ready;
    private boolean notificationSetup;
    private boolean writing;
    private boolean claimed;
    private boolean started;
    private final Runnable deadline = () -> fail("ble_operation_timeout");

    public BleSession(Context context, String address) {
        this.context = context.getApplicationContext();
        this.address = address;
    }

    static void requirePermission(Context context, String permission) {
        if (context.checkSelfPermission(permission) != PackageManager.PERMISSION_GRANTED)
            throw new SecurityException("Bluetooth permission required");
    }

    @Override public synchronized void start() {
        if (started || closed) throw new IllegalStateException("Session is single use");
        started = true;
        thread.start();
        handler = new Handler(thread.getLooper());
        handler.post(() -> {
            try {
                if (Build.VERSION.SDK_INT >= 31)
                    requirePermission(context, Manifest.permission.BLUETOOTH_CONNECT);
                BluetoothManager manager = (BluetoothManager) context.getSystemService(Context.BLUETOOTH_SERVICE);
                BluetoothAdapter adapter = manager == null ? null : manager.getAdapter();
                if (adapter == null || !adapter.isEnabled()) { fail("bluetooth_disabled"); return; }
                BluetoothDevice device = adapter.getRemoteDevice(address);
                if (!DeviceAccess.claimBle(address, this)) { fail("device_busy"); return; }
                claimed = true;
                armDeadline();
                gatt = device.connectGatt(context, false, callback, BluetoothDevice.TRANSPORT_LE);
                if (gatt == null) fail("ble_connect_failed");
            } catch (SecurityException error) { fail("bluetooth_permission_required"); }
            catch (Exception error) { fail("ble_connect_failed"); }
        });
    }

    private void armDeadline() {
        handler.removeCallbacks(deadline);
        handler.postDelayed(deadline, 15000);
    }

    private void fail(String reason) {
        if (closed) return;
        emit("error", null, reason);
        closeOnHandler();
    }

    /** Dispatch all GATT state mutations in order, including callbacks from old/closed GATTs. */
    private void dispatch(BluetoothGatt source, Runnable action) {
        Handler active = handler;
        if (active == null) return;
        active.post(() -> {
            if (closed || source != gatt) return;
            try { action.run(); }
            catch (SecurityException error) { fail("bluetooth_permission_required"); }
            catch (Exception error) { fail("ble_operation_failed"); }
        });
    }

    private final BluetoothGattCallback callback = new BluetoothGattCallback() {
        @Override public void onConnectionStateChange(BluetoothGatt source, int status, int state) {
            dispatch(source, () -> {
                if (status != BluetoothGatt.GATT_SUCCESS || state == BluetoothProfile.STATE_DISCONNECTED) {
                    fail("ble_disconnected");
                } else if (state == BluetoothProfile.STATE_CONNECTED) {
                    armDeadline();
                    if (!source.discoverServices()) fail("service_discovery_failed");
                }
            });
        }

        @Override public void onServicesDiscovered(BluetoothGatt source, int status) {
            dispatch(source, () -> {
                BluetoothGattService service = source.getService(SERVICE);
                if (status != BluetoothGatt.GATT_SUCCESS || service == null) { fail("companion_service_missing"); return; }
                rx = service.getCharacteristic(RX);
                tx = service.getCharacteristic(TX);
                cccd = tx == null ? null : tx.getDescriptor(CCCD);
                if (rx == null || tx == null || cccd == null
                    || (rx.getProperties() & BluetoothGattCharacteristic.PROPERTY_WRITE) == 0
                    || (tx.getProperties() & BluetoothGattCharacteristic.PROPERTY_NOTIFY) == 0) {
                    fail("companion_characteristics_missing"); return;
                }
                armDeadline();
                if (!source.requestMtu(512)) fail("mtu_request_failed");
            });
        }

        @Override public void onMtuChanged(BluetoothGatt source, int value, int status) {
            dispatch(source, () -> {
                if (status != BluetoothGatt.GATT_SUCCESS || value < 53) { fail("mtu_too_small"); return; }
                mtu = value;
                // Android may report an already-negotiated MTU immediately on
                // attaching another GATT client, before service discovery ends.
                // Wait for our explicit request after characteristics are known.
                if (tx == null || cccd == null || notificationSetup) return;
                notificationSetup = true;
                armDeadline();
                if (!source.setCharacteristicNotification(tx, true)) { fail("notification_setup_failed"); return; }
                cccd.setValue(BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE);
                if (!source.writeDescriptor(cccd)) fail("notification_setup_failed");
            });
        }

        @Override public void onDescriptorWrite(BluetoothGatt source, BluetoothGattDescriptor descriptor, int status) {
            dispatch(source, () -> {
                if (descriptor != cccd) return;
                if (status != BluetoothGatt.GATT_SUCCESS) { fail("notification_setup_failed"); return; }
                handler.removeCallbacks(deadline);
                ready = true;
                emit("ready", null, "ble");
            });
        }

        @Override public void onCharacteristicWrite(BluetoothGatt source, BluetoothGattCharacteristic characteristic, int status) {
            dispatch(source, () -> {
                if (characteristic != rx || !writing) return;
                if (status != BluetoothGatt.GATT_SUCCESS) { fail("ble_write_failed"); return; }
                handler.removeCallbacks(deadline);
                writing = false;
                emit("written", null, "ble");
            });
        }

        @Override public void onCharacteristicChanged(BluetoothGatt source, BluetoothGattCharacteristic characteristic) {
            byte[] value = characteristic.getValue();
            received(source, characteristic, value == null ? null : value.clone());
        }

        @Override public void onCharacteristicChanged(BluetoothGatt source, BluetoothGattCharacteristic characteristic, byte[] value) {
            received(source, characteristic, value == null ? null : value.clone());
        }
    };

    private void received(BluetoothGatt source, BluetoothGattCharacteristic characteristic, byte[] value) {
        dispatch(source, () -> {
            if (characteristic == tx && value != null && value.length > 0)
                emit("data", value, "ble");
        });
    }

    @Override public synchronized void send(byte[] data) {
        if (closed || handler == null) throw new IllegalStateException("BLE is disconnected");
        final byte[] copy = data.clone();
        handler.post(() -> {
            if (closed) return;
            if (!ready || writing || copy.length == 0 || copy.length > Math.min(mtu - 3, 300)) {
                fail("ble_write_not_ready_or_oversize"); return;
            }
            try {
                writing = true;
                rx.setWriteType(BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT);
                rx.setValue(copy);
                armDeadline();
                if (!gatt.writeCharacteristic(rx)) fail("ble_write_failed");
            } catch (SecurityException error) { fail("bluetooth_permission_required"); }
            catch (Exception error) { fail("ble_write_failed"); }
        });
    }

    private void closeOnHandler() {
        if (closed) return;
        closed = true;
        ready = false;
        handler.removeCallbacksAndMessages(null);
        if (gatt != null) {
            try { gatt.disconnect(); } catch (Exception ignored) {}
            try { gatt.close(); } catch (Exception ignored) {}
            gatt = null;
        }
        if (claimed) { DeviceAccess.releaseBle(address, this); claimed = false; }
        emit("closed", null, "ble_closed");
        thread.quitSafely();
    }

    @Override public synchronized void close() {
        if (handler == null) { closed = true; return; }
        handler.post(this::closeOnHandler);
    }
}
