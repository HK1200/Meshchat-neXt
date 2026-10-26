package com.meshchatnext;

import android.app.Notification;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.IBinder;

import androidx.annotation.Nullable;
import androidx.core.app.NotificationCompat;

public class MeshChatForegroundService extends Service {
    private static final int FG_NOTIFICATION_ID = 0x4d434801;

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
        return START_STICKY;
    }

    @Override
    public void onTimeout(int startId, int foregroundServiceType) {
        // Android 15+ requires a timed-out service to stop promptly.
        stopForeground(STOP_FOREGROUND_REMOVE);
        stopSelf();
    }

    private Notification buildForegroundNotification() {
        PendingIntent pi = PendingIntent.getActivity(
            this,
            0,
            new Intent(this, MainActivity.class).setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP),
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );
        return new NotificationCompat.Builder(this, MeshChatApplication.CHANNEL_ID_BACKGROUND)
            .setSmallIcon(R.drawable.ic_stat_meshchatnext)
            .setContentTitle(getString(R.string.notification_background_title))
            .setContentText(getString(R.string.notification_background_text))
            .setOngoing(true)
            .setContentIntent(pi)
            .build();
    }

    @Nullable
    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public void onDestroy() {
        stopForeground(STOP_FOREGROUND_REMOVE);
        super.onDestroy();
    }
}
