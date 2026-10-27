package com.meshchatnext;

import android.app.Activity;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.*;
import android.content.pm.*;
import android.net.Uri;
import android.os.*;
import android.provider.Settings;
import android.widget.*;
import java.io.*;
import java.security.MessageDigest;
import java.util.*;
import org.json.JSONObject;

/** Non-exported, user-approved installer handoff for a staged, verified neXt APK. */
public final class UpdateInstallerActivity extends Activity {
    private static final String PREFS = "verified_update_installer";
    private static final String CALLBACK = "com.meshchatnext.UPDATE_INSTALL_RESULT";
    private static final int PERMISSION = 9410;
    private static final long LIMIT = 512L * 1024L * 1024L;
    private TextView message;
    private Button proceed;
    private File verified;
    private String digest = "";
    private volatile boolean cancelled;
    private static final java.util.concurrent.atomic.AtomicBoolean ACTIVE = new java.util.concurrent.atomic.AtomicBoolean();
    private boolean ownsSession;

    public static String status(Context context) {
        SharedPreferences prefs = context.getSharedPreferences(PREFS, MODE_PRIVATE);
        try {
            String state = prefs.getString("state", "idle");
            PackageInfo current = context.getPackageManager().getPackageInfo(context.getPackageName(), 0);
            long code = Build.VERSION.SDK_INT >= 28 ? current.getLongVersionCode() : current.versionCode;
            String expected = prefs.getString("sha256", "");
            if (UpdateInstallPolicy.verifyInstalledResult(state, prefs.getString("attempt_sha", ""), expected,
                    prefs.getLong("before_install", 0), current.lastUpdateTime, code,
                    prefs.getLong("target_code", Long.MAX_VALUE))) {
                MessageDigest hash = MessageDigest.getInstance("SHA-256");
                try (InputStream input = new FileInputStream(current.applicationInfo.sourceDir)) {
                    byte[] buffer = new byte[65536]; int count;
                    while ((count = input.read(buffer)) != -1) hash.update(buffer, 0, count);
                }
                StringBuilder actual = new StringBuilder();
                for (byte value : hash.digest()) actual.append(String.format(Locale.ROOT, "%02x", value & 255));
                boolean matched = expected.equals(actual.toString());
                state = matched ? "installed" : "not_applied";
                prefs.edit().putString("state", state).putString("message", matched
                    ? "The app was updated successfully."
                    : "A different app build is installed. This downloaded APK has not been confirmed as applied.").apply();
            }
            return new JSONObject().put("state", state).put("message", prefs.getString("message", ""))
                .put("sha256", prefs.getString("sha256", "")).toString();
        } catch (Exception e) { return "{\"state\":\"failed\",\"message\":\"Could not check installation status.\"}"; }
    }
    private void state(String value, String text) {
        getSharedPreferences(PREFS, MODE_PRIVATE).edit().putString("state", value)
            .putString("message", text).putString("sha256", digest).apply();
        runOnUiThread(() -> { if (!isFinishing()) message.setText(text); });
    }
    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        ownsSession = ACTIVE.compareAndSet(false, true);
        if (!ownsSession) { finish(); return; }
        LinearLayout layout = new LinearLayout(this); layout.setOrientation(LinearLayout.VERTICAL);
        int pad = (int)(24 * getResources().getDisplayMetrics().density); layout.setPadding(pad, pad, pad, pad);
        TextView title = new TextView(this); title.setText("Install Meshchat neXt update"); title.setTextSize(22); layout.addView(title);
        message = new TextView(this); message.setText("Checking the verified update…"); layout.addView(message);
        proceed = new Button(this); proceed.setText("Continue installation"); proceed.setEnabled(false);
        proceed.setOnClickListener(v -> continueInstallation()); layout.addView(proceed);
        Button close = new Button(this); close.setText("Close"); close.setOnClickListener(v -> {
            cancelled = true;
            String current = getSharedPreferences(PREFS, MODE_PRIVATE).getString("state", "idle");
            if ("preparing".equals(current) || "permission_required".equals(current))
                state("cancelled", "Installation cancelled. The downloaded update remains available in the app.");
            finish();
        }); layout.addView(close);
        ScrollView scroll = new ScrollView(this); scroll.addView(layout); setContentView(scroll);
        if (CALLBACK.equals(getIntent().getAction())) handleResult(getIntent());
        else new Thread(() -> prepare(saved == null), "next-verify-installer").start();
    }
    private boolean inside(File candidate, File root) throws IOException {
        return root != null && candidate.getCanonicalPath().startsWith(root.getCanonicalPath() + File.separator);
    }
    private void prepare(boolean launch) {
        File temporary = null;
        try {
            JSONObject requested = new JSONObject(getIntent().getStringExtra("pending"));
            digest = requested.getString("sha256"); long size = requested.getLong("size");
            // Completion metadata belongs to one verified attempt, never a previous APK.
            getSharedPreferences(PREFS, MODE_PRIVATE).edit().remove("before_install")
                .remove("target_code").remove("attempt_sha").apply();
            if (!digest.matches("[0-9a-f]{64}") || size <= 0 || size > LIMIT
                || !"apk".equals(requested.getString("kind"))) throw new IOException();
            File source = new File(requested.getString("path")).getCanonicalFile();
            if (!source.isFile() || !source.getName().toLowerCase(Locale.ROOT).endsWith(".apk")
                || (!inside(source, getFilesDir()) && !inside(source, getExternalFilesDir(null)))
                || !"pending".equals(source.getParentFile().getName())
                || !"updates".equals(source.getParentFile().getParentFile().getName())) throw new IOException();
            File marker = new File(source.getParentFile().getParentFile(), "pending.json");
            if (marker.length() > 65536) throw new IOException();
            byte[] metadata = new byte[(int)marker.length()];
            try (DataInputStream input = new DataInputStream(new FileInputStream(marker))) { input.readFully(metadata); }
            JSONObject staged = new JSONObject(new String(metadata, java.nio.charset.StandardCharsets.UTF_8));
            if (!digest.equals(staged.getString("sha256")) || size != staged.getLong("size")
                || !source.getName().equals(staged.getString("file")) || !"apk".equals(staged.getString("kind"))
                || !"android".equals(staged.getString("platform"))) throw new IOException();
            state("preparing", "Rechecking the downloaded APK before opening Android’s installer…");
            temporary = File.createTempFile("next-update-", ".apk", getCacheDir());
            MessageDigest hash = MessageDigest.getInstance("SHA-256"); long written = 0;
            try (InputStream input = new FileInputStream(source); OutputStream output = new FileOutputStream(temporary)) {
                byte[] buffer = new byte[65536]; int count;
                while ((count = input.read(buffer)) != -1) {
                    if (cancelled || (written += count) > size) throw new IOException();
                    output.write(buffer, 0, count); hash.update(buffer, 0, count);
                }
            }
            StringBuilder actual = new StringBuilder(); for (byte b : hash.digest()) actual.append(String.format(Locale.ROOT, "%02x", b & 255));
            if (!UpdateInstallPolicy.checksum(digest, actual.toString(), size, written)) throw new IOException();
            PackageManager pm = getPackageManager();
            int flags = Build.VERSION.SDK_INT >= 28 ? PackageManager.GET_SIGNING_CERTIFICATES : PackageManager.GET_SIGNATURES;
            PackageInfo archive = pm.getPackageArchiveInfo(temporary.getPath(), flags);
            PackageInfo installed = pm.getPackageInfo(getPackageName(), flags);
            if (archive == null || !getPackageName().equals(archive.packageName)) throw new IOException();
            long target = Build.VERSION.SDK_INT >= 28 ? archive.getLongVersionCode() : archive.versionCode;
            long current = Build.VERSION.SDK_INT >= 28 ? installed.getLongVersionCode() : installed.versionCode;
            if (!UpdateInstallPolicy.packageMatches(getPackageName(), archive.packageName, current, target,
                signers(installed), signers(archive))) throw new IOException();
            File shared = new File(getCacheDir(), "apk_share"); if (!shared.isDirectory() && !shared.mkdirs()) throw new IOException();
            File destination = new File(shared, "verified-update.apk");
            if (destination.exists() && !destination.delete()) throw new IOException();
            if (!temporary.renameTo(destination)) throw new IOException(); temporary = null; verified = destination;
            getSharedPreferences(PREFS, MODE_PRIVATE).edit().putString("attempt_sha", digest).putLong("target_code", target)
                .putLong("before_install", installed.lastUpdateTime).apply();
            runOnUiThread(() -> { if (!cancelled && !isFinishing()) { proceed.setEnabled(true); if (launch) continueInstallation(); } });
        } catch (Exception error) { if (!cancelled) state("failed", "The update could not be verified for this app. Download it again, or use Save file and open it from Downloads."); }
        finally { if (temporary != null) temporary.delete(); }
    }
    private Set<String> signers(PackageInfo info) throws Exception {
        Signature[] signatures = Build.VERSION.SDK_INT >= 28
            ? (info.signingInfo == null ? null : info.signingInfo.getApkContentsSigners()) : info.signatures;
        Set<String> result = new HashSet<>();
        if (signatures != null) for (Signature signature : signatures)
            result.add(android.util.Base64.encodeToString(MessageDigest.getInstance("SHA-256").digest(signature.toByteArray()), android.util.Base64.NO_WRAP));
        return result;
    }
    private void continueInstallation() {
        if (verified == null || !verified.isFile()) return;
        try {
            if (Build.VERSION.SDK_INT >= 26 && !getPackageManager().canRequestPackageInstalls()) {
                state("permission_required", "Android needs permission to install updates from Meshchat neXt. Allow it on the next screen, then return here. The app has not been updated yet.");
                startActivityForResult(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                    Uri.parse("package:" + getPackageName())), PERMISSION); return;
            }
            proceed.setEnabled(false);
            state("preparing", "Preparing the verified update for Android’s installer…");
            new Thread(this::installSession, "next-stage-installer").start();
        } catch (Exception error) { state("failed", "Android’s installer could not be opened. Use Save file and open the APK from Downloads instead."); }
    }
    private void installSession() {
        try {
            // Session installation preserves the user's existing full-screen calling choice.
            // Never grant this permission to an app whose user has not already allowed it.
            PackageInstaller installer = getPackageManager().getPackageInstaller();
            PackageInstaller.SessionParams params = new PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL);
            params.setAppPackageName(getPackageName()); params.setSize(verified.length());
            if (Build.VERSION.SDK_INT >= 31) params.setRequireUserAction(PackageInstaller.SessionParams.USER_ACTION_REQUIRED);
            if (Build.VERSION.SDK_INT >= 34) {
                NotificationManager notifications = getSystemService(NotificationManager.class);
                params.setPermissionState(android.Manifest.permission.USE_FULL_SCREEN_INTENT,
                    notifications != null && notifications.canUseFullScreenIntent()
                        ? PackageInstaller.SessionParams.PERMISSION_STATE_GRANTED
                        : PackageInstaller.SessionParams.PERMISSION_STATE_DENIED);
            }
            int id = installer.createSession(params);
            String token = UUID.randomUUID().toString();
            getSharedPreferences(PREFS, MODE_PRIVATE).edit().putInt("session_id", id)
                .putString("session_token", token).apply();
            try (PackageInstaller.Session session = installer.openSession(id)) {
                try (InputStream input = new FileInputStream(verified);
                     OutputStream output = session.openWrite("base.apk", 0, verified.length())) {
                    byte[] buffer = new byte[65536]; int count;
                    while ((count = input.read(buffer)) != -1) {
                        if (cancelled) throw new IOException("Installation preparation cancelled");
                        output.write(buffer, 0, count);
                    }
                    session.fsync(output);
                }
                Intent callback = new Intent(this, UpdateInstallerActivity.class).setAction(CALLBACK)
                    .setData(Uri.parse("next-update://result/" + token))
                    .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
                int flags = PendingIntent.FLAG_UPDATE_CURRENT;
                if (Build.VERSION.SDK_INT >= 31) flags |= PendingIntent.FLAG_MUTABLE;
                PendingIntent result = PendingIntent.getActivity(this, id, callback, flags);
                if (cancelled) throw new IOException("Installation preparation cancelled");
                state("installer_opened", "Android’s installer is open. Review and approve the update there; downloading alone does not install it.");
                session.commit(result.getIntentSender());
            } catch (Exception error) { installer.abandonSession(id); throw error; }
        } catch (Exception error) {
            if (!cancelled) state("failed", "Android’s installer could not be opened. Use Save file and open the APK from Downloads instead.");
        }
    }
    @Override protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent); setIntent(intent);
        if (CALLBACK.equals(intent.getAction())) handleResult(intent);
    }
    private void handleResult(Intent intent) {
        SharedPreferences prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        String token = intent.getData() == null ? "" : intent.getData().getLastPathSegment();
        if (!UpdateInstallPolicy.sessionResultMatches(prefs.getInt("session_id", -1),
                intent.getIntExtra(PackageInstaller.EXTRA_SESSION_ID, -2),
                prefs.getString("session_token", ""), token)) { finish(); return; }
        digest = prefs.getString("sha256", "");
        int result = intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE);
        if (result == PackageInstaller.STATUS_PENDING_USER_ACTION) {
            Intent confirmation = intent.getParcelableExtra(Intent.EXTRA_INTENT);
            if (confirmation == null) { state("failed", "Android did not provide an installation confirmation."); return; }
            // Session callbacks, not Activity result codes, are authoritative.
            startActivity(confirmation);
        } else if (result == PackageInstaller.STATUS_SUCCESS) {
            // Check the actual installed bytes before reporting success.
            status(this); message.setText(prefs.getString("message", "Android completed the update."));
        } else {
            state(result == PackageInstaller.STATUS_FAILURE_ABORTED ? "cancelled" : "failed",
                result == PackageInstaller.STATUS_FAILURE_ABORTED
                    ? "Installation was cancelled. The downloaded update remains available in the app."
                    : "Android did not complete the installation. Return to Updates to retry.");
        }
    }
    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request == PERMISSION) {
            if (Build.VERSION.SDK_INT < 26 || getPackageManager().canRequestPackageInstalls()) continueInstallation();
            else state("permission_required", "Install permission was not granted. Tap Continue installation to retry, or use Save file in the app.");

        }
    }
    @Override public void onDestroy() { cancelled = true; if (ownsSession) ACTIVE.set(false); super.onDestroy(); }
}
