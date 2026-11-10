package com.meshchatnext;

import android.media.AudioDeviceCallback;
import android.media.AudioDeviceInfo;
import android.media.AudioManager;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;

/** Owns the selected communication route for one native call session. */
final class TelephoneBluetoothRoute {
    private static final String TAG = "MeshchatNextCallRoute";
    private final AudioManager manager;
    private boolean active;
    private boolean speakerRequested;
    private boolean lastRequestAccepted;
    private boolean registered;
    private boolean routeOwned;
    private int selectedId = -1;
    private final AudioDeviceCallback callback = new AudioDeviceCallback() {
        @Override public void onAudioDevicesAdded(AudioDeviceInfo[] devices) { refresh(); }
        @Override public void onAudioDevicesRemoved(AudioDeviceInfo[] devices) { refresh(); }
    };

    TelephoneBluetoothRoute(AudioManager manager) { this.manager = manager; }

    synchronized void start() {
        if (active) return;
        active = true;
        try {
            manager.registerAudioDeviceCallback(callback, new Handler(Looper.getMainLooper()));
            registered = true;
        } catch (RuntimeException e) {
            Log.w(TAG, "Could not watch call audio devices", e);
        }
        refresh();
    }

    synchronized boolean setSpeaker(boolean enabled) {
        if (!active) return false;
        speakerRequested = enabled;
        clearRoute();
        refresh();
        return lastRequestAccepted;
    }

    synchronized boolean isSpeakerOn() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            AudioDeviceInfo device = manager.getCommunicationDevice();
            return device != null && device.getType() == AudioDeviceInfo.TYPE_BUILTIN_SPEAKER;
        }
        return manager.isSpeakerphoneOn();
    }

    private synchronized void refresh() {
        if (!active) return;
        lastRequestAccepted = true;
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                AudioDeviceInfo chosen = null;
                for (AudioDeviceInfo device : manager.getAvailableCommunicationDevices()) {
                    int type = device.getType();
                    if (speakerRequested ? type == AudioDeviceInfo.TYPE_BUILTIN_SPEAKER
                            : type == AudioDeviceInfo.TYPE_BLE_HEADSET || type == AudioDeviceInfo.TYPE_BLUETOOTH_SCO) {
                        if (chosen == null || device.getId() == selectedId) chosen = device;
                    }
                }
                if (chosen != null) {
                    if (routeOwned && chosen.getId() == selectedId) return;
                    boolean accepted = manager.setCommunicationDevice(chosen);
                    lastRequestAccepted = accepted;
                    Log.i(TAG, "Call audio route requested: " + accepted);
                    if (accepted) {
                        routeOwned = true;
                        selectedId = chosen.getId();
                    }
                } else if (routeOwned) {
                    manager.clearCommunicationDevice();
                    routeOwned = false;
                    selectedId = -1;
                    Log.i(TAG, "Bluetooth disconnected; restored default call route");
                }
            } else {
                if (speakerRequested) {
                    manager.setSpeakerphoneOn(true);
                    routeOwned = true;
                    return;
                }
                boolean available = false;
                for (AudioDeviceInfo device : manager.getDevices(AudioManager.GET_DEVICES_OUTPUTS)) {
                    if (device.getType() == AudioDeviceInfo.TYPE_BLUETOOTH_SCO) available = true;
                }
                if (available && !routeOwned) {
                    manager.startBluetoothSco();
                    routeOwned = true;
                    manager.setBluetoothScoOn(true);
                } else if (!available && routeOwned) {
                    clearRoute();
                }
            }
        } catch (RuntimeException e) {
            lastRequestAccepted = false;
            Log.w(TAG, "Call audio route unavailable; keeping default audio", e);
        }
    }

    synchronized void stop() {
        active = false;
        if (registered) {
            try { manager.unregisterAudioDeviceCallback(callback); }
            catch (RuntimeException e) { Log.w(TAG, "Could not remove audio device callback", e); }
            registered = false;
        }
        clearRoute();
    }

    private void clearRoute() {
        if (!routeOwned) return;
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                manager.clearCommunicationDevice();
            } else {
                manager.stopBluetoothSco();
                manager.setBluetoothScoOn(false);
                manager.setSpeakerphoneOn(false);
            }
        } catch (RuntimeException e) {
            Log.w(TAG, "Could not clear Bluetooth call route", e);
        } finally {
            routeOwned = false;
            selectedId = -1;
        }
    }
}
