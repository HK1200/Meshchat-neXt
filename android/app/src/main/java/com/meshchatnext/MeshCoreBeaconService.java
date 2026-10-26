package com.meshchatnext;

import android.Manifest;
import android.app.Notification;
import android.app.AlarmManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.pm.ServiceInfo;
import android.location.Location;
import android.location.LocationListener;
import android.location.LocationManager;
import android.os.Build;
import android.os.Bundle;
import android.os.IBinder;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import androidx.core.app.NotificationCompat;
import androidx.core.content.ContextCompat;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;
import okhttp3.MediaType;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;
import org.json.JSONObject;

/** Explicit, non-persistent Android location foreground session. Never boot-started. */
public final class MeshCoreBeaconService extends Service implements LocationListener {
    private static final int NOTIFICATION = 0x4d434862;
    public static volatile boolean active = false;
    public static volatile String status = "Off";
    public static volatile int submittedCount = 0;
    public static volatile long lastSubmittedElapsed = -1;
    private AlarmManager alarms;
    private PendingIntent expiryIntent;
    private final Handler expiryHandler = new Handler(Looper.getMainLooper());
    private final Runnable expire = () -> { status = "Stopped · scheduled duration reached"; stopSelf(); };
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private final AtomicBoolean sending = new AtomicBoolean(false);
    private LocationManager locations;
    private volatile boolean stopped = false;
    private String owner, token, csrf, cookie;
    private int interval = 300;
    private volatile long last = -1;
    private long expiresElapsed = -1;

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && "expire".equals(intent.getAction())) { status = "Stopped · scheduled duration reached"; stopSelf(); return START_NOT_STICKY; }
        if (intent == null || "stop".equals(intent.getAction()) || active) { stopSelf(); return START_NOT_STICKY; }
        try {
            owner = intent.getStringExtra("owner"); token = intent.getStringExtra("token");
            csrf = intent.getStringExtra("csrf"); cookie = intent.getStringExtra("cookie");
            interval = intent.getIntExtra("interval", 300);
            int duration = intent.getIntExtra("durationMinutes", 0);
            if (!(duration == 0 || duration == 15 || duration == 30 || duration == 60)) throw new IllegalArgumentException();
            submittedCount = 0; lastSubmittedElapsed = -1;
            expiresElapsed = duration > 0 ? SystemClock.elapsedRealtime() + duration * 60000L : -1;
            if (duration > 0) {
                expiryHandler.postDelayed(expire, duration * 60000L);
                alarms = (AlarmManager) getSystemService(ALARM_SERVICE);
                expiryIntent = PendingIntent.getService(this, NOTIFICATION + 1,
                    new Intent(this, MeshCoreBeaconService.class).setAction("expire"),
                    PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
                // Elapsed time includes sleep. Inexact idle delivery needs no new alarm permission.
                // Every fix also checks the deadline, so delayed cleanup cannot send past it.
                alarms.setAndAllowWhileIdle(AlarmManager.ELAPSED_REALTIME_WAKEUP, expiresElapsed, expiryIntent);
            }
            if (owner == null || !owner.matches("[0-9a-f]{64}") || token == null || !token.matches("[0-9a-f]{64}") || csrf == null || csrf.isEmpty() || !(interval == 60 || interval == 120 || interval == 300)) throw new IllegalArgumentException();
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED && ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_COARSE_LOCATION) != PackageManager.PERMISSION_GRANTED) throw new SecurityException();
            PendingIntent stop = PendingIntent.getService(this, NOTIFICATION, new Intent(this, MeshCoreBeaconService.class).setAction("stop"), PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
            PendingIntent open = PendingIntent.getActivity(this, NOTIFICATION, new Intent(this, MainActivity.class), PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
            Notification notification = new NotificationCompat.Builder(this, MeshChatApplication.CHANNEL_ID_BACKGROUND)
                .setSmallIcon(R.drawable.ic_stat_meshchatnext).setContentTitle("MeshCore · Position sharing")
                .setContentText("Sharing with your private team every " + interval + " seconds")
                .setOngoing(true).setContentIntent(open).addAction(0, "Stop sharing", stop).build();
            if (Build.VERSION.SDK_INT >= 29) startForeground(NOTIFICATION, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION);
            else startForeground(NOTIFICATION, notification);
            locations = (LocationManager) getSystemService(LOCATION_SERVICE);
            String provider = locations.isProviderEnabled(LocationManager.GPS_PROVIDER) ? LocationManager.GPS_PROVIDER : LocationManager.NETWORK_PROVIDER;
            if (!locations.isProviderEnabled(provider)) throw new IllegalStateException();
            // Keep GNSS sampling below Android's long-interval hibernation threshold.
            // RF transmission remains independently rate-limited by the selected interval.
            locations.requestLocationUpdates(provider, 5000L, 0, this);
            active = true; status = "Waiting for a current location";
        } catch (RuntimeException error) { status = "Stopped · check location permission and settings"; stopSelf(); }
        return START_NOT_STICKY;
    }

    @Override public void onLocationChanged(Location location) {
        if (stopped || !active || location == null || !location.hasAccuracy() || location.getAccuracy() > 255) return;
        long now = SystemClock.elapsedRealtime();
        if (expiresElapsed >= 0 && now >= expiresElapsed) { status = "Stopped · scheduled duration reached"; stopSelf(); return; }
        if (!MeshCoreBeaconPolicy.shouldSend(now, location.getElapsedRealtimeNanos(), location.getAccuracy(), last, interval) || !sending.compareAndSet(false, true)) return;
        last = now;
        worker.execute(() -> {
            MeshChatWakeLock.acquire(this, "meshcore-beacon");
            try {
                if (stopped) return;
                JSONObject body = new JSONObject().put("expected_owner", owner).put("token", token)
                    .put("latitude", location.getLatitude()).put("longitude", location.getLongitude())
                    .put("accuracy", location.getAccuracy()).put("timestamp", location.getTime());
                Request.Builder builder = new Request.Builder().url("https://127.0.0.1:8012/api/v1/meshcore/team-beacon-position")
                    .header("X-CSRF-Token", csrf).post(RequestBody.create(body.toString(), MediaType.get("application/json")));
                if (cookie != null && !cookie.isEmpty()) builder.header("Cookie", cookie);
                try (Response response = LocalhostTrustOkHttpClient.get().newCall(builder.build()).execute()) {
                    if (!response.isSuccessful() || response.body() == null) throw new IllegalStateException();
                    JSONObject result = new JSONObject(response.body().string()).getJSONObject("result");
                    String state = result.optString("state");
                    if (!"submitted".equals(state) && !"waiting".equals(state)) throw new IllegalStateException();
                    if (stopped) return;
                    // Start the next minimum interval after backend radio submission.
                    // Measuring from before HTTP could arrive slightly early and skip a whole interval.
                    last = SystemClock.elapsedRealtime();
                    if ("submitted".equals(state)) {
                        submittedCount++; lastSubmittedElapsed = SystemClock.elapsedRealtime();
                        status = "Position submitted · channel delivery is not acknowledged";
                    } else status = "Waiting for the next send interval";
                }
            } catch (Exception error) {
                if (!stopped) {
                    status = "Stopped · connection or team settings changed";
                    stopped = true; active = false; stopSelf();
                }
            } finally { sending.set(false); MeshChatWakeLock.release("meshcore-beacon"); }
        });
    }
    @Override public void onProviderDisabled(String provider) { status = "Stopped · location disabled"; stopSelf(); }
    @Override public void onProviderEnabled(String provider) {}
    @Override public void onStatusChanged(String provider, int state, Bundle extras) {}
    @Override public IBinder onBind(Intent intent) { return null; }
    @Override public void onDestroy() {
        expiryHandler.removeCallbacksAndMessages(null);
        if (alarms != null && expiryIntent != null) { alarms.cancel(expiryIntent); expiryIntent.cancel(); }
        stopped = true; if (active && !status.startsWith("Stopped")) status = "Off"; active = false;
        if (locations != null) try { locations.removeUpdates(this); } catch (RuntimeException ignored) {}
        final String stopOwner = owner, stopToken = token, stopCsrf = csrf, stopCookie = cookie;
        if (stopToken != null && stopCsrf != null) worker.execute(() -> {
            try {
                JSONObject body = new JSONObject().put("expected_owner", stopOwner).put("token", stopToken);
                Request.Builder request = new Request.Builder().url("https://127.0.0.1:8012/api/v1/meshcore/team-beacon-stop")
                    .header("X-CSRF-Token", stopCsrf).post(RequestBody.create(body.toString(), MediaType.get("application/json")));
                if (stopCookie != null && !stopCookie.isEmpty()) request.header("Cookie", stopCookie);
                try (Response ignored = LocalhostTrustOkHttpClient.get().newCall(request.build()).execute()) { }
            } catch (Exception ignored) { /* Backend loss already invalidates the consent session. */ }
        });
        worker.shutdown(); token = null; csrf = null; cookie = null;
        stopForeground(STOP_FOREGROUND_REMOVE); super.onDestroy();
    }
}
