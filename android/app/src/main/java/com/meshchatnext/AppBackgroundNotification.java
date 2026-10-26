package com.meshchatnext;

import android.app.ActivityManager;
import android.app.Notification;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import androidx.core.app.NotificationCompat;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;

/** One status entry shared by the app and its independent SIP foreground service. */
public final class AppBackgroundNotification {
    public static final int ID = 0x4d434801;
    public static final int LEGACY_SIP_ID = 6400;
    private static final Object STATUS_LOCK = new Object();
    private static final String STATUS_FILE = "sip-background-status";
    private AppBackgroundNotification() {}

    public static String sipLine(String network, String state, String call) {
        String detail = call != null && !call.isEmpty() && !"idle".equals(call) && !"ended".equals(call)
            ? call : state;
        String line = "SIP" + (network == null || network.isEmpty() ? "" : " · " + network)
            + (detail == null || detail.isEmpty() ? "" : " · " + detail.replace('_', ' '));
        line = line.replace('\n', ' ').replace('\r', ' ');
        return line.substring(0, Math.min(line.length(), 160));
    }

    public static Notification build(Context context) {
        String status = "";
        if (isForeground(context, "com.meshchatnext.sip.SipService")) {
            try (FileInputStream in = new FileInputStream(new File(context.getFilesDir(), STATUS_FILE))) {
                byte[] buffer = new byte[1025];
                int count = in.read(buffer);
                if (count > 0 && count <= 1024) status = new String(buffer, 0, count, StandardCharsets.UTF_8);
            } catch (java.io.IOException ignored) { }
        }
        return build(context, status);
    }

    public static Notification build(Context context, String status) {
        Intent app = new Intent(context, MainActivity.class)
            .setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent open = PendingIntent.getActivity(context, 0, app,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        String text = context.getString(R.string.notification_background_text);
        NotificationCompat.Builder builder = new NotificationCompat.Builder(context, MeshChatApplication.CHANNEL_ID_BACKGROUND)
            .setSmallIcon(R.drawable.ic_stat_meshchatnext)
            .setContentTitle(context.getString(R.string.notification_background_title))
            .setContentText(text).setOngoing(true).setOnlyAlertOnce(true).setContentIntent(open);
        if (status != null && !status.isEmpty()) {
            Intent sip = new Intent(context, MainActivity.class).setAction(Intent.ACTION_VIEW)
                .setData(Uri.parse("meshchatnext://app/call?network=sip"))
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
            PendingIntent openSip = PendingIntent.getActivity(context, 6400, sip,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
            builder.setSubText(status).setStyle(new NotificationCompat.BigTextStyle().bigText(text + "\n" + status))
                .addAction(0, "Open SIP", openSip);
        }
        return builder.build();
    }

    /** The two processes share only non-secret display text, committed with rename. */
    public static void saveSipStatus(Context context, String status) {
        synchronized (STATUS_LOCK) {
            File target = new File(context.getFilesDir(), STATUS_FILE);
            File temp = new File(context.getFilesDir(), STATUS_FILE + "." + android.os.Process.myPid() + ".tmp");
            try {
                try (FileOutputStream out = new FileOutputStream(temp)) {
                    out.write(status.getBytes(StandardCharsets.UTF_8));
                    out.getFD().sync();
                }
                if (!temp.renameTo(target)) throw new java.io.IOException("Status commit failed");
            } catch (java.io.IOException ignored) {
                // Notification status must never interrupt a call or registration.
            } finally { if (temp.exists()) temp.delete(); }
        }
    }

    public static void clearSipStatus(Context context) {
        synchronized (STATUS_LOCK) { new File(context.getFilesDir(), STATUS_FILE).delete(); }
        if (isForeground(context, "com.meshchatnext.MeshChatForegroundService")) {
            context.getSystemService(NotificationManager.class).notify(ID, build(context, ""));
        }
    }

    @SuppressWarnings("deprecation")
    private static boolean isForeground(Context context, String className) {
        try {
            ActivityManager manager = context.getSystemService(ActivityManager.class);
            if (manager == null) return false;
            // Android restricts this API to our own services; no other app is queried.
            for (ActivityManager.RunningServiceInfo service : manager.getRunningServices(100)) {
                if (service.foreground && context.getPackageName().equals(service.service.getPackageName())
                    && className.equals(service.service.getClassName())) return true;
            }
        } catch (RuntimeException ignored) { }
        return false;
    }
}
