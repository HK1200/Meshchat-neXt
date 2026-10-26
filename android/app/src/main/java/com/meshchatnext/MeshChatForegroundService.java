package com.meshchatnext;

import android.app.Notification;
import android.app.Service;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.IBinder;

import androidx.annotation.Nullable;

public class MeshChatForegroundService extends Service {
    private static final int FG_NOTIFICATION_ID = AppBackgroundNotification.ID;
    private final android.os.Handler statusHandler = new android.os.Handler(android.os.Looper.getMainLooper());
    private boolean refreshingStatus;
    private final Runnable refreshStatus = new Runnable() {
        @Override public void run() {
            getSystemService(android.app.NotificationManager.class).notify(FG_NOTIFICATION_ID, buildForegroundNotification());
            statusHandler.postDelayed(this, 30000);
        }
    };

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        Notification notification = buildForegroundNotification();
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(
                FG_NOTIFICATION_ID,
                notification,
                // Keep external mesh links alive; this is not a bounded data-sync job.
                // The manifest already declares connectedDevice and its prerequisites.
                ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE
            );
        } else {
            startForeground(FG_NOTIFICATION_ID, notification);
        }
        if (!refreshingStatus) {
            refreshingStatus = true;
            statusHandler.postDelayed(refreshStatus, 30000);
        }
        return START_STICKY;
    }

    @Override
    public void onTimeout(int startId, int foregroundServiceType) {
        // Android 15+ requires a timed-out service to stop promptly.
        stopForeground(STOP_FOREGROUND_REMOVE);
        stopSelf();
    }

    private Notification buildForegroundNotification() {
        return AppBackgroundNotification.build(this);
    }

    @Nullable
    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public void onDestroy() {
        statusHandler.removeCallbacks(refreshStatus);
        stopForeground(STOP_FOREGROUND_REMOVE);
        super.onDestroy();
    }
}
