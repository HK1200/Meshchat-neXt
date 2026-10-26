package com.meshchatnext.meshcore;

import android.content.Context;
import android.hardware.usb.UsbDevice;
import android.hardware.usb.UsbDeviceConnection;
import android.hardware.usb.UsbManager;
import com.hoho.android.usbserial.driver.UsbSerialDriver;
import com.hoho.android.usbserial.driver.UsbSerialPort;
import com.hoho.android.usbserial.driver.UsbSerialProber;
import com.meshchatnext.radio.DeviceAccess;
import java.io.IOException;
import java.util.Arrays;

/** Dedicated serial port and reader. Explicit device path; never selects or probes an RNode. */
public final class UsbSession extends NativeSession {
    private final Context context;
    private final String deviceName;
    private final int portIndex;
    private final int baud;
    private final boolean dtr;
    private final boolean rts;
    private UsbSerialPort port;
    private UsbDeviceConnection connection;
    private boolean started;

    public UsbSession(Context context, String deviceName, int portIndex, int baud,
                      boolean dtr, boolean rts) {
        this.context = context.getApplicationContext();
        this.deviceName = deviceName;
        this.portIndex = portIndex;
        this.baud = baud;
        this.dtr = dtr;
        this.rts = rts;
    }

    @Override public synchronized void start() {
        if (started || closed) throw new IllegalStateException("Session is single use");
        started = true;
        try {
            UsbManager manager = (UsbManager) context.getSystemService(Context.USB_SERVICE);
            UsbDevice device = manager == null ? null : manager.getDeviceList().get(deviceName);
            if (device == null) throw new IOException("device_missing");
            if (!manager.hasPermission(device)) throw new IOException("usb_permission_required");
            UsbSerialDriver driver = UsbSerialProber.getDefaultProber().probeDevice(device);
            if (driver == null || portIndex < 0 || portIndex >= driver.getPorts().size())
                throw new IOException("serial_port_missing");
            if (baud <= 0) throw new IOException("invalid_baud");
            connection = DeviceAccess.openUsb(context, device);
            if (connection == null) throw new IOException("device_busy_or_unavailable");
            port = driver.getPorts().get(portIndex);
            port.open(connection);
            port.setParameters(baud, 8, UsbSerialPort.STOPBITS_1, UsbSerialPort.PARITY_NONE);
            port.setDTR(dtr);
            port.setRTS(rts);
            emit("ready", null, "usb");
            Thread reader = new Thread(this::readLoop, "meshcore-usb-reader");
            reader.setDaemon(true);
            reader.start();
        } catch (Exception error) {
            emit("error", null, error instanceof IOException ? error.getMessage() : "usb_open_failed");
            close();
        }
    }

    private String connectionFailure(String fallback) {
        UsbManager manager = (UsbManager) context.getSystemService(Context.USB_SERVICE);
        UsbDevice device = manager == null ? null : manager.getDeviceList().get(deviceName);
        if (device == null) return "usb_detached";
        if (!manager.hasPermission(device)) return "usb_permission_required";
        return fallback;
    }

    private void readLoop() {
        byte[] buffer = new byte[1024];
        try {
            while (!closed) {
                UsbSerialPort active;
                synchronized (this) { active = port; }
                if (active == null) break;
                int count = active.read(buffer, 200);
                if (count > 0 && !closed) emit("data", Arrays.copyOf(buffer, count), "usb");
            }
        } catch (Exception error) {
            if (!closed) emit("error", null, connectionFailure("usb_read_failed"));
        } finally {
            close();
        }
    }

    @Override public synchronized void send(byte[] data) {
        if (closed || port == null) throw new IllegalStateException("USB is disconnected");
        if (data.length < 4 || data.length > 303) throw new IllegalArgumentException("Invalid frame");
        try {
            port.write(data, 5000);
            emit("written", null, "usb");
        } catch (Exception error) {
            emit("error", null, connectionFailure("usb_write_failed"));
            close();
        }
    }

    @Override public synchronized void close() {
        if (closed) return;
        closed = true;
        if (port != null) {
            try { port.close(); } catch (IOException ignored) {}
            port = null;
        }
        if (connection != null) {
            connection.close();
            connection = null;
        }
        emit("closed", null, "usb_closed");
    }
}
