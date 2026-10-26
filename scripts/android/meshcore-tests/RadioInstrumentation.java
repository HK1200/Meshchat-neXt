package com.meshchatnext.meshcore;

import android.app.Instrumentation;
import android.content.Context;
import android.os.Bundle;
import com.meshchatnext.radio.DeviceAccess;
import java.util.ArrayList;
import java.util.List;

/** Separate, disposable package exercising the exact production native transport classes. */
public final class RadioInstrumentation extends Instrumentation {
    private Bundle arguments;
    @Override public void onCreate(Bundle args) { arguments = args; start(); }

    @Override public void onStart() {
        Bundle result = new Bundle();
        try {
            Context context = getTargetContext();
            String mode = arguments.getString("mode", "scan");
            if (mode.equals("scan")) {
                BleDiscovery discovery = new BleDiscovery(context);
                List<String> addresses = new ArrayList<>();
                try {
                    discovery.start();
                    long end = System.nanoTime() + 5000000000L;
                    while (System.nanoTime() < end) {
                        NativeSession.Event event = discovery.poll(200);
                        if (event == null) continue;
                        if (event.kind.equals("error")) throw new IllegalStateException(event.detail);
                        String label = event.detail + "|" + (event.data == null ? "" : new String(event.data, java.nio.charset.StandardCharsets.UTF_8));
                        if (event.kind.equals("found") && !addresses.contains(label)) addresses.add(label);
                    }
                } finally { discovery.close(); }
                result.putString("addresses", String.join(",", addresses));
                result.putInt("usb_devices", UsbDevices.list(context).length);
            } else if (mode.equals("ownership")) {
                String address = "00:11:22:33:44:55";
                Object rnode = new Object();
                DeviceAccess.claimBle(address, rnode);
                BleSession blocked = new BleSession(context, address);
                try {
                    blocked.start();
                    NativeSession.Event event = next(blocked);
                    if (!event.kind.equals("error") || !event.detail.equals("device_busy"))
                        throw new IllegalStateException("Radio ownership guard failed");
                    awaitClosed(blocked);
                    if (DeviceAccess.claimBle(address, blocked))
                        throw new IllegalStateException("Closing MeshCore released the RNode claim");
                } finally { blocked.close(); DeviceAccess.releaseBle(address, rnode); }
                Object replacement = new Object();
                if (!DeviceAccess.claimBle(address, replacement))
                    throw new IllegalStateException("RNode claim was not released");
                DeviceAccess.releaseBle(address, replacement);
                result.putString("ownership", "busy_rejected_other_owner_preserved");
            } else if (mode.equals("ble")) {
                String address = arguments.getString("target", "");
                if (address.isEmpty()) throw new IllegalArgumentException("Explicit BLE target required");
                Object rnode = new Object();
                if (!DeviceAccess.claimBle(address, rnode)) throw new IllegalStateException("Unexpected existing claim");
                BleSession blocked = new BleSession(context, address);
                try {
                    blocked.start();
                    NativeSession.Event event = next(blocked);
                    if (!event.kind.equals("error") || !event.detail.equals("device_busy"))
                        throw new IllegalStateException("Radio ownership guard failed");
                    awaitClosed(blocked);
                } finally { blocked.close(); DeviceAccess.releaseBle(address, rnode); }
                // Repeat a full connection with fresh GATT clients to catch stale subscriptions and claims.
                for (int round = 0; round < 2; round++) {
                    BleSession session = new BleSession(context, address);
                    try {
                        session.start();
                        NativeSession.Event ready = next(session);
                        if (!ready.kind.equals("ready")) throw new IllegalStateException("Expected ready: " + ready.detail);
                        exchange(session, new byte[] {1,3,32,32,32,32,32,32,72,75}, 5);
                        exchange(session, new byte[] {22,3}, 13);
                    } finally { session.close(); awaitClosed(session); }
                    if (!DeviceAccess.claimBle(address, rnode)) throw new IllegalStateException("Leaked BLE ownership");
                    DeviceAccess.releaseBle(address, rnode);
                }
                result.putString("ble", "handshake_query_reconnect_passed");
                result.putString("ownership", "busy_rejected_and_released");
            } else if (mode.equals("usb-missing")) {
                UsbSession session = new UsbSession(context, "/dev/bus/usb/missing", 0, 115200, true, false);
                session.start();
                NativeSession.Event event = next(session);
                if (!event.kind.equals("error") || !event.detail.equals("device_missing"))
                    throw new IllegalStateException("Missing USB device not rejected");
                awaitClosed(session);
                result.putString("usb_missing", "passed");
            } else throw new IllegalArgumentException("Unknown mode");
            result.putString("status", "passed");
            finish(-1, result);
        } catch (Throwable error) {
            result.putString("status", "failed");
            result.putString("failure", error.getClass().getSimpleName() + ": " + error.getMessage());
            finish(0, result);
        }
    }

    private NativeSession.Event next(NativeSession session) throws Exception {
        long end = System.nanoTime() + 25000000000L;
        while (System.nanoTime() < end) {
            NativeSession.Event event = session.poll(200);
            if (event != null) return event;
        }
        throw new IllegalStateException("Native event timeout");
    }

    private void awaitClosed(NativeSession session) throws Exception {
        for (int i = 0; i < 32; i++) {
            NativeSession.Event event = next(session);
            if (event.kind.equals("closed")) return;
        }
        throw new IllegalStateException("Native close not observed");
    }

    private void exchange(NativeSession session, byte[] command, int expectedType) throws Exception {
        session.send(command);
        boolean written = false, replied = false;
        long end = System.nanoTime() + 25000000000L;
        while ((!written || !replied) && System.nanoTime() < end) {
            NativeSession.Event event = session.poll(200);
            if (event == null) continue;
            if (event.kind.equals("error") || event.kind.equals("closed"))
                throw new IllegalStateException(event.detail);
            if (event.kind.equals("written")) written = true;
            if (event.kind.equals("data") && event.data != null && event.data.length > 0) {
                if (event.data[0] == 1) throw new IllegalStateException("Companion command rejected");
                if ((event.data[0] & 255) == expectedType) replied = true;
            }
        }
        if (!written || !replied) throw new IllegalStateException("Companion response timeout");
    }
}
