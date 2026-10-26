package com.meshchatnext.meshcore;

import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.hardware.usb.UsbDevice;
import android.hardware.usb.UsbManager;
import com.hoho.android.usbserial.driver.UsbSerialDriver;
import com.hoho.android.usbserial.driver.UsbSerialProber;
import java.util.ArrayList;
import java.util.List;

/** Discovery never opens serial ports or writes a protocol probe. */
public final class UsbDevices {
    private UsbDevices() {}

    public static String[] list(Context context) {
        UsbManager manager = (UsbManager) context.getSystemService(Context.USB_SERVICE);
        List<String> paths = new ArrayList<>();
        if (manager != null) for (UsbSerialDriver driver : UsbSerialProber.getDefaultProber().findAllDrivers(manager))
            paths.add(driver.getDevice().getDeviceName());
        return paths.toArray(new String[0]);
    }

    public static boolean hasPermission(Context context, String path) {
        UsbManager manager = (UsbManager) context.getSystemService(Context.USB_SERVICE);
        UsbDevice device = manager == null ? null : manager.getDeviceList().get(path);
        return device != null && manager.hasPermission(device);
    }

    public static void requestPermission(Context context, String path) {
        UsbManager manager = (UsbManager) context.getSystemService(Context.USB_SERVICE);
        UsbDevice device = manager == null ? null : manager.getDeviceList().get(path);
        if (device == null) throw new IllegalArgumentException("USB device missing");
        if (manager.hasPermission(device)) return;
        Intent intent = new Intent(context.getPackageName() + ".MESHCORE_USB_PERMISSION")
            .setPackage(context.getPackageName());
        PendingIntent pending = PendingIntent.getBroadcast(context, device.getDeviceId(), intent,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        manager.requestPermission(device, pending);
    }
}
