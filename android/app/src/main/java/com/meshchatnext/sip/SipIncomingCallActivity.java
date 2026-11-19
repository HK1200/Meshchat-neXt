package com.meshchatnext.sip;

import android.Manifest;
import android.app.Activity;
import android.app.KeyguardManager;
import android.net.Uri;
import com.meshchatnext.MainActivity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.os.*;
import android.view.*;
import android.widget.*;
import org.json.JSONObject;

/** Explicit incoming-call UI, including above the lock screen. Never answers implicitly. */
public final class SipIncomingCallActivity extends Activity {
    private final Handler handler = new Handler(Looper.getMainLooper());
    private SipController controller;
    private String token;
    private long initialStatusVersion;
    private TextView status;
    private Button answer, end, speaker, mute, open;
    private boolean handoffStarted;
    private boolean answerRequested, autoAnswer, ready;
    private final Runnable refresh = new Runnable() {
        public void run() {
            if (isFinishing()) return;
            try {
                JSONObject value = new JSONObject(controller.status());
                String live = value.optString("call_token"), state = value.optString("call_state");
                boolean fresh = controller.statusVersion() > initialStatusVersion;
                if (fresh && !live.isEmpty() && !token.equals(live)) { finish(); return; }
                ready = token.equals(live);
                if (ready) {
                    if ("connected".equals(state)) {
                        status.setText("SIP call connected");
                        answer.setVisibility(View.GONE);
                        end.setText("End call");
                        speaker.setVisibility(View.VISIBLE);
                        mute.setVisibility(View.VISIBLE);
                        open.setVisibility(View.VISIBLE);
                        speaker.setText(value.optBoolean("speaker") ? "Speaker on" : "Speaker off");
                        mute.setText(value.optBoolean("muted") ? "Unmute" : "Mute");
                        handoffIfUnlocked(value);
                        getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
                    } else status.setText(answerRequested ? "Answering SIP call…" : "Incoming SIP call");
                    answer.setEnabled(!answerRequested);
                    end.setEnabled(true);
                    if (autoAnswer) { autoAnswer = false; answer(); }
                } else if (fresh && "idle".equals(state) && !value.optString("selected").isEmpty()) {
                    finish(); return;
                }
            } catch (Exception ignored) { }
            handler.postDelayed(this, 250);
        }
    };
    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        setVolumeControlStream(android.media.AudioManager.STREAM_VOICE_CALL);
        token = getIntent().getStringExtra("call_token");
        if (token == null || !token.matches("[0-9a-f]{32}")) { finish(); return; }
        autoAnswer = getIntent().getBooleanExtra("answer", false);
        if (Build.VERSION.SDK_INT >= 27) { setShowWhenLocked(true); setTurnScreenOn(true); }
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED
            | WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON | WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setGravity(Gravity.CENTER);
        int padding = (int)(24 * getResources().getDisplayMetrics().density);
        layout.setPadding(padding, padding, padding, padding);
        layout.setBackgroundColor(Color.rgb(20, 24, 30));
        TextView title = new TextView(this); title.setText("Meshchat neXt · SIP");
        title.setTextColor(Color.WHITE); title.setTextSize(24); layout.addView(title);
        status = new TextView(this); status.setText("Incoming SIP call");
        status.setTextColor(Color.WHITE); status.setTextSize(22); layout.addView(status);
        TextView peer = new TextView(this); peer.setText(getIntent().getStringExtra("peer"));
        peer.setTextColor(Color.LTGRAY); peer.setTextSize(18); layout.addView(peer);
        answer = new Button(this); answer.setText("Answer"); answer.setEnabled(false);
        answer.setOnClickListener(v -> answer()); layout.addView(answer);
        end = new Button(this); end.setText("Decline"); end.setEnabled(false);
        end.setOnClickListener(v -> {
            try { controller.send(new JSONObject().put("op", "hangup").put("call_token", token).toString()); }
            catch (Exception ignored) { }
        }); layout.addView(end);
        speaker = new Button(this); speaker.setText("Speaker off");
        speaker.setVisibility(View.GONE);
        speaker.setOnClickListener(v -> toggle("speaker")); layout.addView(speaker);
        mute = new Button(this); mute.setText("Mute"); mute.setVisibility(View.GONE);
        mute.setOnClickListener(v -> toggle("mute")); layout.addView(mute);
        open = new Button(this); open.setText("Open call controls"); open.setVisibility(View.GONE);
        open.setOnClickListener(v -> {
            KeyguardManager keyguard = getSystemService(KeyguardManager.class);
            if (keyguard != null && keyguard.isKeyguardLocked()) {
                if (Build.VERSION.SDK_INT >= 26) {
                    keyguard.requestDismissKeyguard(this, new KeyguardManager.KeyguardDismissCallback() {
                        @Override public void onDismissSucceeded() { openCurrentCall(); }
                    });
                } else status.setText("Unlock your phone to open call controls");
            } else openCurrentCall();
        }); layout.addView(open);
        ScrollView scroll = new ScrollView(this); scroll.setFillViewport(true); scroll.addView(layout);
        setContentView(scroll);
        controller = SipController.get(this);
        initialStatusVersion = controller.statusVersion();
        handler.post(refresh);
    }
    private void toggle(String operation) {
        try {
            JSONObject value = new JSONObject(controller.status());
            if (!SipCallScreenPolicy.active(token, value.optString("call_token"), value.optString("call_state"))) return;
            String stateKey = "mute".equals(operation) ? "muted" : "speaker";
            controller.send(new JSONObject().put("op", operation).put("call_token", token)
                .put("value", !value.optBoolean(stateKey)).toString());
        } catch (Exception ignored) { status.setText("Could not change call audio; try again"); }
    }
    private void openCurrentCall() {
        try { handoffIfUnlocked(new JSONObject(controller.status())); }
        catch (Exception ignored) { status.setText("Could not open call controls; try again"); }
    }
    private void handoffIfUnlocked(JSONObject value) {
        KeyguardManager keyguard = getSystemService(KeyguardManager.class);
        if (handoffStarted || keyguard == null || !SipCallScreenPolicy.canHandoff(token,
                value.optString("call_token"), value.optString("call_state"), keyguard.isKeyguardLocked())) return;
        Intent intent = new Intent(this, MainActivity.class).setAction(Intent.ACTION_VIEW)
            .setData(Uri.parse("meshchatnext://app/call?network=sip"))
            .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        handoffStarted = true;
        try { startActivity(intent); finish(); }
        catch (Exception ignored) { handoffStarted = false; status.setText("Could not open call controls; try again"); }
    }
    private void answer() {
        if (!ready || answerRequested) return;
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, 1); return;
        }
        try {
            JSONObject result = new JSONObject(controller.send(new JSONObject()
                .put("op", "answer").put("call_token", token).toString()));
            answerRequested = result.optBoolean("ok");
            if (!answerRequested) status.setText("Call service starting; tap Answer again");
        } catch (Exception ignored) { status.setText("Could not answer; try again"); }
    }
    @Override public void onRequestPermissionsResult(int request, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(request, permissions, results);
        if (request == 1 && results.length > 0 && results[0] == PackageManager.PERMISSION_GRANTED) answer();
    }
    @Override public void onDestroy() { handler.removeCallbacksAndMessages(null); super.onDestroy(); }
}
