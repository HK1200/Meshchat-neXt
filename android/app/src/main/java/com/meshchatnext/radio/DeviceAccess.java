package com.meshchatnext.radio;

import android.content.Context;
import android.hardware.usb.UsbDevice;
import android.hardware.usb.UsbDeviceConnection;
import android.hardware.usb.UsbManager;
import java.util.HashMap;
import java.util.Map;

/** App-wide hardware guard only: no shared protocol state or connection lifecycle. */
public final class DeviceAccess {
    private static final Map<String, UsbDeviceConnection> USB = new HashMap<>();
    private static final Map<String, Object> BLE = new HashMap<>();

    private DeviceAccess() {}

    /** Return null if already open. Prevent drivers using force-claim from stealing a radio. */
    public static synchronized UsbDeviceConnection openUsb(Context context, UsbDevice device) {
        String key = device.getDeviceName();
        UsbDeviceConnection old = USB.get(key);
        if (old != null && old.getFileDescriptor() >= 0) return null;
        USB.remove(key);
        UsbManager manager = (UsbManager) context.getSystemService(Context.USB_SERVICE);
        UsbDeviceConnection connection = manager == null ? null : manager.openDevice(device);
        if (connection != null) USB.put(key, connection);
        return connection;
    }

    public static synchronized boolean claimBle(String address, Object owner) {
        String key = address.toUpperCase(java.util.Locale.ROOT);
        Object current = BLE.get(key);
        if (current != null && current != owner) return false;
        BLE.put(key, owner);
        return true;
    }

    public static synchronized void releaseBle(String address, Object owner) {
        String key = address.toUpperCase(java.util.Locale.ROOT);
        if (BLE.get(key) == owner) BLE.remove(key);
    }
}
