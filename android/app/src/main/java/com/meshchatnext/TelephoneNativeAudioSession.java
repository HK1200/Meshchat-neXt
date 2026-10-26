package com.meshchatnext;

import android.Manifest;
import android.content.Context;
import android.content.pm.PackageManager;
import android.media.AudioAttributes;
import android.media.AudioFocusRequest;
import android.media.AudioFormat;
import android.media.AudioManager;
import android.media.AudioRecord;
import android.media.AudioTrack;
import android.media.MediaRecorder;
import android.os.Build;
import android.text.TextUtils;
import android.webkit.CookieManager;
import android.webkit.WebView;

import androidx.annotation.Nullable;
import androidx.core.content.ContextCompat;

import org.json.JSONObject;

import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.atomic.AtomicBoolean;

import okhttp3.Request;
import okhttp3.Response;
import okhttp3.WebSocket;
import okhttp3.WebSocketListener;
import okio.ByteString;

/**
 * Native mic send + speaker receive for {@code /ws/telephone/audio} (same protocol as the web
 * audio bridge). Do not use on the UI thread for {@link #start()} other than the initial schedule.
 */
public final class TelephoneNativeAudioSession {
    public static final int SAMPLE_RATE = 48000;
    private static final int IN_CHANNEL = AudioFormat.CHANNEL_IN_MONO;
    private static final int OUT_CHANNEL = AudioFormat.CHANNEL_OUT_MONO;
    private static final int FORMAT = AudioFormat.ENCODING_PCM_16BIT;

    private final Context appContext;
    private final AtomicBoolean running = new AtomicBoolean(false);
    private final AtomicBoolean pipelinesReady = new AtomicBoolean(false);
    private final java.util.concurrent.atomic.AtomicLong sessionGeneration =
        new java.util.concurrent.atomic.AtomicLong(0L);
    // Guarded by this session's monitor.
    private boolean cleanupInProgress = false;
    // Guarded by this session's monitor; initialization runs on the UI thread.
    private boolean initializationInProgress = false;
    // Guarded by this session's monitor; cleanup waits for initialization.
    private boolean cleanupPendingInitialization = false;
    private volatile int microphoneFrameMs = 60;
    private final MainActivity activity;

    @Nullable
    private WebSocket webSocket;
    @Nullable
    private AudioRecord audioRecord;
    @Nullable
    private AudioTrack audioTrack;
    @Nullable
    private Thread sendThread;
    @Nullable
    private Thread connectThread;

    // Keep WebSocket reception independent of AudioTrack playback.
    private static final int PLAYBACK_QUEUE_CAPACITY = 3;
    private final ArrayBlockingQueue<ByteString> playbackQueue =
        new ArrayBlockingQueue<>(PLAYBACK_QUEUE_CAPACITY);
    @Nullable
    private Thread playbackThread;
    @Nullable
    private AudioManager audioManager;
    @Nullable
    private AudioFocusRequest audioFocusRequest;
    @Nullable
    private TelephoneBluetoothRoute bluetoothRoute;
    private final AudioManager.OnAudioFocusChangeListener audioFocusListener = focusChange -> {
    };

    public TelephoneNativeAudioSession(MainActivity activity) {
        this.activity = activity;
        this.appContext = activity.getApplicationContext();
    }

    public static boolean canRun(Context ctx) {
        if (ContextCompat.checkSelfPermission(ctx, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            return false;
        }
        return AudioRecord.getMinBufferSize(SAMPLE_RATE, IN_CHANNEL, FORMAT) > 0;
    }

    public boolean isActive() {
        return running.get();
    }

    public synchronized String start() {
        try {String state=new org.json.JSONObject(com.meshchatnext.sip.SipController.get(appContext).status()).optString("call_state","idle");if(!"idle".equals(state)){postDispatch("error","sip_call_active",null);return "busy";}}catch(Exception ignored){}

        if (cleanupInProgress) {
            return "cleanup_in_progress";
        }
        if (running.get() || connectThread != null) {
            return "busy";
        }
        if (!canRun(appContext)) {
            postDispatch("error", "no_record_audio_permission", null);
            return "no_record_audio_permission";
        }
        final long generation = sessionGeneration.incrementAndGet();
        connectThread = new Thread(
            () -> {
                try {
                    openWebSocket(generation);
                } finally {
                    synchronized (TelephoneNativeAudioSession.this) {
                        if (connectThread == Thread.currentThread()) {
                            connectThread = null;
                        }
                    }
                }
            },
            "meshchatnext-tel-ws"
        );
        connectThread.setPriority(Thread.NORM_PRIORITY);
        connectThread.start();
        return "ok";
    }

    public void stop() {
        final WebSocket socketToClose;

        synchronized (this) {
            final long generation = sessionGeneration.get();
            sessionGeneration.incrementAndGet();
            running.set(false);
            pipelinesReady.set(false);

            socketToClose = webSocket;
            webSocket = null;

            startCleanupWorkerLocked(generation);
        }

        if (socketToClose != null) {
            try {
                socketToClose.close(1000, "client stop");
            } catch (Exception ignored) {
            }
        }
    }

    private void awaitInitializationCompletion() {
        boolean interrupted = false;

        synchronized (this) {
            while (initializationInProgress) {
                try {
                    wait();
                } catch (InterruptedException e) {
                    interrupted = true;
                }
            }
        }

        if (interrupted) {
            Thread.currentThread().interrupt();
        }
    }

    // Must be called while holding this session's monitor.
    private void startCleanupWorkerLocked(long generation) {
        if (cleanupInProgress) {
            return;
        }

        cleanupInProgress = true;

        new Thread(
            () -> {
                try {
                    awaitInitializationCompletion();

                    stopMicrophoneCapture();

                    final Thread microphoneThread;
                    synchronized (TelephoneNativeAudioSession.this) {
                        microphoneThread = sendThread;
                    }

                    if (microphoneThread != null
                            && microphoneThread != Thread.currentThread()) {
                        boolean interrupted = false;
                        boolean timeoutReported = false;
                        final long warningDeadline =
                            android.os.SystemClock.elapsedRealtime() + 5000L;

                        while (microphoneThread.isAlive()) {
                            try {
                                microphoneThread.join(500L);
                            } catch (InterruptedException e) {
                                interrupted = true;
                            }

                            if (!timeoutReported
                                    && microphoneThread.isAlive()
                                    && android.os.SystemClock.elapsedRealtime()
                                        >= warningDeadline) {
                                timeoutReported = true;
                                postDispatchForGeneration(
                                    generation,
                                    "error",
                                    "microphone_shutdown_timeout",
                                    "Microphone worker did not stop within five seconds"
                                );
                            }
                        }

                        if (interrupted) {
                            Thread.currentThread().interrupt();
                        }
                    }

                    synchronized (TelephoneNativeAudioSession.this) {
                        if (sendThread == microphoneThread) {
                            sendThread = null;
                        }
                    }

                    releaseAudio(generation);
                } finally {
                    synchronized (TelephoneNativeAudioSession.this) {
                        cleanupPendingInitialization = false;
                        cleanupInProgress = false;
                    }
                }
            },
            "meshchatnext-tel-cleanup"
        ).start();
    }

    private void postReleaseAfterStop(long generation) {
        synchronized (this) {
            startCleanupWorkerLocked(generation);
        }
    }

    @SuppressWarnings("WeakerAccess")
    void onDestroy() {
        stop();
    }

    private void openWebSocket(long generation) {
        String cookie = "";
        try {
            String c = CookieManager.getInstance().getCookie("https://127.0.0.1:8012");
            if (!TextUtils.isEmpty(c)) {
                cookie = c;
            }
        } catch (Exception ignored) {
        }
        Request.Builder rb = new Request.Builder().url("wss://127.0.0.1:8012/ws/telephone/audio");
        if (!TextUtils.isEmpty(cookie)) {
            rb.addHeader("Cookie", cookie);
        }
        try {
            synchronized (this) {
                if (sessionGeneration.get() != generation) {
                    return;
                }
                running.set(true);
                pipelinesReady.set(false);
                microphoneFrameMs = 60;
                webSocket = LocalhostTrustOkHttpClient.get()
                    .newWebSocket(
                    rb.build(),
                    new WebSocketListener() {
                        @Override
                        public void onOpen(WebSocket w, Response r) {
                            if (sessionGeneration.get() != generation) {
                                w.close(1000, "stale session");
                                return;
                            }
                            w.send("{\"type\":\"attach\"}");
                        }

                        @Override
                        public void onMessage(WebSocket w, String t) {
                            if (sessionGeneration.get() != generation || t == null) {
                                return;
                            }
                            try {
                                JSONObject o = new JSONObject(t);
                                if ("error".equals(o.optString("type"))) {
                                    String msg = o.optString("message", "error");
                                    if (msg.contains("Web audio is disabled")
                                        || (msg.equals("error") && o.length() < 2)) {
                                        // keep generic
                                    }
                                    postDispatchForGeneration(generation, "error", "server", msg);
                                } else if ("web_audio.ready".equals(o.optString("type"))) {
                                    int ms = o.optInt("frame_ms", 60);
                                    if (ms == 10 || ms == 20 || ms == 40 || ms == 60
                                            || ms == 200 || ms == 320 || ms == 400) {
                                        microphoneFrameMs = ms;
                                    }
                                    activity.runOnUiThread(() -> onWebAudioReadyPipelines(generation));
                                }
                            } catch (Exception e) {
                                if (t.contains("web_audio.ready") || t.contains("frame_ms")) {
                                    activity.runOnUiThread(() -> onWebAudioReadyPipelines(generation));
                                }
                            }
                        }

                        @Override
                        public void onMessage(WebSocket w, ByteString bytes) {
                            if (sessionGeneration.get() != generation) {
                                return;
                            }
                            enqueuePlayback(bytes);
                        }

                        @Override
                        public void onFailure(WebSocket w, Throwable t, @Nullable Response r) {
                            synchronized (TelephoneNativeAudioSession.this) {
                                if (sessionGeneration.get() != generation) {
                                    return;
                                }
                                sessionGeneration.incrementAndGet();
                                webSocket = null;
                                running.set(false);
                                pipelinesReady.set(false);
                                postReleaseAfterStop(generation);
                            }
                            String msg = t != null && t.getMessage() != null ? t.getMessage() : "connect_failed";
                            postDispatchForGeneration(generation, "error", "websocket", msg);
                        }

                        @Override
                        public void onClosed(WebSocket w, int c, @Nullable String r) {
                            synchronized (TelephoneNativeAudioSession.this) {
                                if (sessionGeneration.get() != generation) {
                                    return;
                                }
                                sessionGeneration.incrementAndGet();
                                webSocket = null;
                                running.set(false);
                                pipelinesReady.set(false);
                                postReleaseAfterStop(generation);
                            }
                            postDispatchForGeneration(generation, "closed", null, null);
                        }
                    }
                );
            }
        } catch (Exception e) {
            synchronized (this) {
                if (sessionGeneration.get() != generation) {
                    return;
                }
                sessionGeneration.incrementAndGet();
                running.set(false);
                pipelinesReady.set(false);
                webSocket = null;
                startCleanupWorkerLocked(generation);
            }
            String m = e.getMessage() != null ? e.getMessage() : "okhttp";
            postDispatchForGeneration(generation, "error", "connect", m);
        }
    }

    private void failAudioInitialization(
            long generation, String reason, @Nullable String detail) {
        final WebSocket socketToClose;

        synchronized (this) {
            if (sessionGeneration.get() != generation) {
                return;
            }

            sessionGeneration.incrementAndGet();
            running.set(false);
            pipelinesReady.set(false);

            socketToClose = webSocket;
            webSocket = null;

            startCleanupWorkerLocked(generation);
        }

        if (socketToClose != null) {
            try {
                socketToClose.close(1000, "audio setup failed");
            } catch (Exception ignored) {
            }
        }

        postDispatchForGeneration(generation, "error", reason, detail);
    }

    private boolean isCurrentAudioGeneration(long generation) {
        synchronized (this) {
            return sessionGeneration.get() == generation
                && running.get()
                && !cleanupInProgress;
        }
    }

    private void onWebAudioReadyPipelines(long generation) {
        synchronized (this) {
            if (sessionGeneration.get() != generation
                    || !running.get()
                    || cleanupInProgress
                    || initializationInProgress) {
                return;
            }
            if (pipelinesReady.getAndSet(true)) {
                return;
            }
            initializationInProgress = true;
        }
        try {
            if (ContextCompat.checkSelfPermission(appContext, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
                failAudioInitialization(
                    generation, "no_record_audio_permission", null
                );
                return;
            }
            acquireCallAudioMode();
            int inBuf = Math.max(
                AudioRecord.getMinBufferSize(SAMPLE_RATE, IN_CHANNEL, FORMAT),
                4096
            );
            audioRecord = createVoiceAudioRecord(inBuf);
            if (audioRecord == null) {
                failAudioInitialization(
                    generation, "no_record_audio_permission", null
                );
                return;
            }
            if (audioRecord.getState() != AudioRecord.STATE_INITIALIZED) {
                failAudioInitialization(generation, "record_init", null);
                return;
            }
            int outMin = AudioTrack.getMinBufferSize(SAMPLE_RATE, OUT_CHANNEL, FORMAT);
            if (outMin <= 0) {
                outMin = 4096;
            }
            int trackBuf = Math.max(outMin * 2, outMin);
            AudioAttributes playbackAttr = new AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                .build();
            AudioFormat trackFmt = new AudioFormat.Builder()
                .setSampleRate(SAMPLE_RATE)
                .setEncoding(FORMAT)
                .setChannelMask(OUT_CHANNEL)
                .build();
            synchronized (playbackLock) {
                if (!running.get()) {
                    return;
                }
                audioTrack = new AudioTrack.Builder()
                    .setAudioAttributes(playbackAttr)
                    .setAudioFormat(trackFmt)
                    .setBufferSizeInBytes(trackBuf)
                    .setTransferMode(AudioTrack.MODE_STREAM)
                    .build();
                if (audioTrack.getState() == AudioTrack.STATE_INITIALIZED) {
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
                        try {
                            audioTrack.setVolume(AudioTrack.getMaxVolume());
                        } catch (Exception ignored) {
                        }
                    }
                }
            }
            boolean trackInitialized;
            synchronized (playbackLock) {
                trackInitialized = running.get()
                    && audioTrack != null
                    && audioTrack.getState() == AudioTrack.STATE_INITIALIZED;
            }
            if (!trackInitialized) {
                if (running.get()) {
                    failAudioInitialization(generation, "track_init", null);
                }
                return;
            }
            if (!isCurrentAudioGeneration(generation)) {
                return;
            }

            try {
                audioRecord.startRecording();
            } catch (Exception e) {
                failAudioInitialization(
                    generation, "record_start",
                    e.getMessage() != null ? e.getMessage() : ""
                );
                return;
            }
            try {
                synchronized (playbackLock) {
                    if (!running.get() || audioTrack == null) {
                        return;
                    }
                    audioTrack.play();
                }
            } catch (Exception e) {
                failAudioInitialization(
                    generation, "track_start",
                    e.getMessage() != null ? e.getMessage() : ""
                );
                return;
            }
            synchronized (this) {
                if (sessionGeneration.get() != generation
                        || !running.get()
                        || cleanupInProgress) {
                    return;
                }

                startPlaybackWorker();
                sendThread = new Thread(() -> drainMicrophone(generation), "meshchatnext-tel-mic");
                sendThread.setPriority(Thread.NORM_PRIORITY);
                sendThread.start();
            }

            postReadyForGeneration(generation);
        } catch (Exception e) {
            failAudioInitialization(
                generation, "setup",
                e.getMessage() != null ? e.getMessage() : "setup"
            );
        } finally {
            synchronized (this) {
                initializationInProgress = false;
                notifyAll();
            }
        }
    }

    @Nullable
    private AudioRecord createVoiceAudioRecord(int inBuf) {
        if (ContextCompat.checkSelfPermission(appContext, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            return null;
        }
        return new AudioRecord(
            MediaRecorder.AudioSource.VOICE_COMMUNICATION,
            SAMPLE_RATE,
            IN_CHANNEL,
            FORMAT,
            inBuf * 2
        );
    }

    private void drainMicrophone(long generation) {
        byte[] buf = new byte[4096];
        PcmFrameAccumulator accumulator =
            new PcmFrameAccumulator(SAMPLE_RATE, microphoneFrameMs);
        long lastLevelsMs = 0L;
        while (running.get() && webSocket != null) {
            AudioRecord ar;
            WebSocket w;
            synchronized (this) {
                ar = audioRecord;
                w = webSocket;
            }
            if (ar == null || w == null) {
                break;
            }
            int n;
            try {
                n = ar.read(buf, 0, buf.length);
            } catch (Exception e) {
                break;
            }
            if (n > 0 && w != null) {
                try {
                    accumulator.append(buf, n, frame -> {
                        if (running.get() && webSocket == w) {
                            w.send(ByteString.of(frame));
                        }
                    });
                } catch (Exception e) {
                    break;
                }
                long now = System.currentTimeMillis();
                if (now - lastLevelsMs >= 200L) {
                    lastLevelsMs = now;
                    float tx = pcmPeakLevel(buf, n);
                    postLevels(generation, tx, lastRxLevel);
                }
            } else if (n < 0) {
                break;
            }
        }
    }

    private volatile float lastRxLevel = 0f;
    private final Object playbackLock = new Object();

    private void stopPlaybackWorker(long generation) {
        playbackQueue.clear();

        Thread worker = playbackThread;
        if (worker != null) {
            worker.interrupt();

            if (worker != Thread.currentThread()) {
                boolean interrupted = false;
                boolean timeoutReported = false;
                final long warningDeadline =
                    android.os.SystemClock.elapsedRealtime() + 5000L;

                while (worker.isAlive()) {
                    try {
                        worker.join(500L);
                    } catch (InterruptedException e) {
                        interrupted = true;
                    }

                    if (!timeoutReported
                            && worker.isAlive()
                            && android.os.SystemClock.elapsedRealtime()
                                >= warningDeadline) {
                        timeoutReported = true;
                        postDispatchForGeneration(
                            generation,
                            "error",
                            "playback_shutdown_timeout",
                            "Playback worker did not stop within five seconds"
                        );
                    }
                }

                if (interrupted) {
                    Thread.currentThread().interrupt();
                }
            }

            if (!worker.isAlive()) {
                playbackThread = null;
            }
        }
    }

    private void startPlaybackWorker() {
        if (playbackThread != null && playbackThread.isAlive()) {
            return;
        }

        final long generation = sessionGeneration.get();
        playbackQueue.clear();

        Thread worker = new Thread(() -> {
            try {
                while (sessionGeneration.get() == generation
                        && running.get()) {
                    ByteString packet;
                    try {
                        packet = playbackQueue.poll(
                            100L, java.util.concurrent.TimeUnit.MILLISECONDS
                        );
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        break;
                    }

                    if (packet != null
                            && sessionGeneration.get() == generation
                            && running.get()) {
                        playPcm(packet, generation);
                    }
                }
            } finally {
                if (sessionGeneration.get() == generation) {
                    playbackQueue.clear();
                }
            }
        }, "meshchatnext-tel-playback");

        playbackThread = worker;
        worker.start();
    }

    private void enqueuePlayback(ByteString bytes) {
        if (bytes == null || bytes.size() == 0 || !running.get()) {
            return;
        }

        if (!playbackQueue.offer(bytes)) {
            // Drop the oldest waiting audio instead of increasing latency.
            playbackQueue.poll();
            playbackQueue.offer(bytes);
        }
    }

    private void playPcm(ByteString bytes, long generation) {
        if (bytes == null || bytes.size() == 0
                || !isCurrentAudioGeneration(generation)) {
            return;
        }

        byte[] raw = bytes.toByteArray();
        lastRxLevel = pcmPeakLevel(raw, raw.length);

        int offset = 0;
        while (offset < raw.length
                && isCurrentAudioGeneration(generation)) {
            int written;
            synchronized (playbackLock) {
                if (sessionGeneration.get() != generation
                        || !running.get()
                        || audioTrack == null) {
                    return;
                }
                try {
                    written = audioTrack.write(
                        raw,
                        offset,
                        raw.length - offset,
                        AudioTrack.WRITE_NON_BLOCKING
                    );
                } catch (IllegalStateException e) {
                    return;
                }
            }

            if (written < 0) {
                return;
            }
            if (written == 0) {
                try {
                    Thread.sleep(2L);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return;
                }
                continue;
            }
            offset += written;
        }
    }

    private static float pcmPeakLevel(byte[] pcm, int length) {
        if (pcm == null || length < 2) {
            return 0f;
        }
        int peak = 0;
        int end = length - (length % 2);
        for (int i = 0; i < end; i += 2) {
            int sample = (pcm[i] & 0xff) | (pcm[i + 1] << 8);
            if (sample > 32767) {
                sample -= 65536;
            }
            int abs = sample < 0 ? -sample : sample;
            if (abs > peak) {
                peak = abs;
            }
        }
        return Math.min(1f, peak / 32767f);
    }

    private void postLevels(long generation, float tx, float rx) {
        activity.runOnUiThread(() -> {
            if (!isCurrentAudioGeneration(generation)) {
                return;
            }
            dispatchLevels(generation, tx, rx);
        });
    }

    private void dispatchLevels(long generation, float tx, float rx) {
        try {
            WebView wv = activity.getWebViewForNativeBridge();
            if (wv == null) {
                return;
            }
            JSONObject o = new JSONObject();
            o.put("type", "meshchatnext-native-telephone-audio");
            o.put("kind", "levels");
            o.put("generation", generation);
            o.put("tx_level", tx);
            o.put("rx_level", rx);
            String j = o.toString();
            wv.evaluateJavascript(
                "try{var d=" + j + ";"
                    + "window.dispatchEvent(new CustomEvent('meshchatnext-native-telephone-audio',{detail:d}));}catch(e){}",
                null
            );
        } catch (Exception ignored) {
        }
    }

    private void postReadyForGeneration(long generation) {
        activity.runOnUiThread(() -> {
            if (!isCurrentAudioGeneration(generation)) {
                return;
            }
            dispatchToPage(generation, "ready", null, null);
        });
    }

    private void postDispatch(String a, @Nullable String b, @Nullable String c) {
        final long generation = sessionGeneration.get();
        postDispatchForGeneration(generation, a, b, c);
    }

    private void postDispatchForGeneration(
            long generation,
            String kind,
            @Nullable String sub,
            @Nullable String detail) {
        activity.runOnUiThread(
            () -> dispatchToPage(generation, kind, sub, detail)
        );
    }

    private void dispatchToPage(
            long generation,
            String kind,
            @Nullable String sub,
            @Nullable String detail) {
        try {
            WebView wv = activity.getWebViewForNativeBridge();
            if (wv == null) {
                return;
            }
            JSONObject o = new JSONObject();
            o.put("type", "meshchatnext-native-telephone-audio");
            o.put("kind", kind);
            o.put("generation", generation);
            if (sub != null) {
                o.put("sub", sub);
            }
            if (detail != null) {
                o.put("detail", detail);
            }
            String j = o.toString();
            wv.evaluateJavascript(
                "try{var d=" + j + ";"
                    + "window.dispatchEvent(new CustomEvent('meshchatnext-native-telephone-audio',{detail:d}));}catch(e){}",
                null
            );
        } catch (Exception ignored) {
        }
    }

    private void acquireCallAudioMode() {
        releaseCallAudioMode();
        audioManager = (AudioManager) appContext.getSystemService(Context.AUDIO_SERVICE);
        if (audioManager == null) {
            return;
        }
        try {
            audioManager.setMode(AudioManager.MODE_IN_COMMUNICATION);
        } catch (Exception ignored) {
        }
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                AudioAttributes aa = new AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build();
                audioFocusRequest = new AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT)
                    .setAudioAttributes(aa)
                    .setAcceptsDelayedFocusGain(false)
                    .build();
                audioManager.requestAudioFocus(audioFocusRequest);
            } else {
                audioManager.requestAudioFocus(
                    audioFocusListener,
                    AudioManager.STREAM_VOICE_CALL,
                    AudioManager.AUDIOFOCUS_GAIN_TRANSIENT
                );
            }
        } catch (Exception ignored) {
        }
        bluetoothRoute = new TelephoneBluetoothRoute(audioManager);
        bluetoothRoute.start();
    }

    private void releaseCallAudioMode() {
        if (bluetoothRoute != null) {
            bluetoothRoute.stop();
            bluetoothRoute = null;
        }
        if (audioManager == null) {
            return;
        }
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && audioFocusRequest != null) {
                audioManager.abandonAudioFocusRequest(audioFocusRequest);
            } else {
                audioManager.abandonAudioFocus(audioFocusListener);
            }
        } catch (Exception ignored) {
        }
        try {
            audioManager.setMode(AudioManager.MODE_NORMAL);
        } catch (Exception ignored) {
        }
        audioFocusRequest = null;
        audioManager = null;
    }

    private void stopMicrophoneCapture() {
        final AudioRecord recorder;

        synchronized (this) {
            recorder = audioRecord;
        }

        if (recorder == null) {
            return;
        }

        try {
            if (recorder.getRecordingState()
                    == AudioRecord.RECORDSTATE_RECORDING) {
                recorder.stop();
            }
        } catch (Exception ignored) {
        }
    }

    private void releaseTx(long generation) {
        stopPlaybackWorker(generation);

        if (audioRecord != null) {
            try {
                if (audioRecord.getRecordingState() == AudioRecord.RECORDSTATE_RECORDING) {
                    audioRecord.stop();
                }
            } catch (Exception ignored) {
            }
            try {
                audioRecord.release();
            } catch (Exception ignored) {
            }
            audioRecord = null;
        }
        synchronized (playbackLock) {
            AudioTrack track = audioTrack;
            audioTrack = null;

            if (track != null) {
                try {
                    if (track.getPlayState() == AudioTrack.PLAYSTATE_PLAYING) {
                        track.stop();
                    }
                } catch (Exception ignored) {
                }
                try {
                    track.release();
                } catch (Exception ignored) {
                }
            }
        }
        releaseCallAudioMode();
    }

    private void releaseAudio(long generation) {
        releaseTx(generation);
    }
}