// SPDX-License-Identifier: 0BSD
package com.meshchatnext;

import android.content.Context;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.speech.tts.TextToSpeech;
import android.speech.tts.UtteranceProgressListener;
import android.speech.tts.Voice;
import java.io.File;
import java.util.Locale;
import java.util.Set;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

/** Offline voicemail synthesis. Blocking methods must run on a Python worker thread. */
public final class VoicemailTextToSpeech {
    private static final Handler MAIN = new Handler(Looper.getMainLooper());
    private VoicemailTextToSpeech() {}

    private static TextToSpeech open() throws Exception {
        if (Looper.myLooper() == Looper.getMainLooper()) {
            throw new IllegalStateException("Speech generation must run on a worker thread");
        }
        Context context = MeshChatApplication.getAppContext();
        if (context == null) throw new IllegalStateException("Android application is not ready");
        CountDownLatch initialized = new CountDownLatch(1);
        AtomicReference<TextToSpeech> engine = new AtomicReference<>();
        AtomicReference<String> failure = new AtomicReference<>();
        MAIN.post(() -> {
            try {
                engine.set(new TextToSpeech(context, status -> {
                    if (status != TextToSpeech.SUCCESS) failure.set("Android speech engine could not start");
                    initialized.countDown();
                }));
            } catch (Exception e) {
                failure.set(e.getMessage());
                initialized.countDown();
            }
        });
        try {
            if (!initialized.await(10, TimeUnit.SECONDS)) throw new IllegalStateException("Android speech engine timed out");
            if (failure.get() != null || engine.get() == null) {
                throw new IllegalStateException(failure.get() == null ? "No Android speech engine installed" : failure.get());
            }
            return engine.get();
        } catch (Exception e) {
            // Queue cleanup behind creation, including when the main thread was busy.
            MAIN.post(() -> { if (engine.get() != null) engine.get().shutdown(); });
            throw e;
        }
    }

    private static Voice offlineVoice(TextToSpeech engine, String requested) {
        Set<Voice> voices = engine.getVoices();
        if (voices == null) return null;
        String language = requested == null ? "" : requested.trim();
        Locale locale = language.isEmpty() ? Locale.getDefault() : Locale.forLanguageTag(language.replace('_', '-'));
        Voice fallback = null;
        Voice matchingLanguage = null;
        Voice current = engine.getVoice();
        for (Voice voice : voices) {
            if (voice.isNetworkConnectionRequired() || (voice.getFeatures() != null && voice.getFeatures().contains(TextToSpeech.Engine.KEY_FEATURE_NOT_INSTALLED))) continue;
            if (fallback == null || voice.equals(current)) fallback = voice;
            if (voice.getName().equals(language) || voice.getLocale().equals(locale)) return voice;
            if (voice.getLocale().getLanguage().equals(locale.getLanguage())) matchingLanguage = voice;
        }
        return matchingLanguage != null ? matchingLanguage : (language.isEmpty() ? fallback : null);
    }

    public static boolean isAvailable() {
        TextToSpeech engine = null;
        try {
            engine = open();
            return offlineVoice(engine, "") != null;
        } catch (Exception e) {
            return false;
        } finally {
            if (engine != null) engine.shutdown();
        }
    }

    public static void synthesize(String text, String outputPath, String voice, int speed, int pitch) throws Exception {
        if (text == null || text.trim().isEmpty()) throw new IllegalArgumentException("Enter a greeting first");
        if (text.length() > TextToSpeech.getMaxSpeechInputLength()) throw new IllegalArgumentException("Greeting is too long for Android speech");
        TextToSpeech engine = open();
        File output = new File(outputPath);
        boolean complete = false;
        try {
            Voice selected = offlineVoice(engine, voice);
            if (selected == null) throw new IllegalStateException("No installed offline voice matches this language. Install voice data in Android speech settings.");
            if (engine.setVoice(selected) != TextToSpeech.SUCCESS) throw new IllegalStateException("Could not select Android voice");
            engine.setSpeechRate(Math.max(0.4f, Math.min(2.6f, speed / 175f)));
            engine.setPitch(Math.max(0.5f, Math.min(2f, pitch / 50f)));
            CountDownLatch done = new CountDownLatch(1);
            AtomicReference<String> error = new AtomicReference<>();
            engine.setOnUtteranceProgressListener(new UtteranceProgressListener() {
                @Override public void onStart(String id) {}
                @Override public void onDone(String id) { done.countDown(); }
                @Override public void onError(String id) { error.set("Android speech generation failed"); done.countDown(); }
                @Override public void onError(String id, int code) { error.set("Android speech generation failed (" + code + ")"); done.countDown(); }
            });
            int result = engine.synthesizeToFile(text, new Bundle(), output, "meshchatnext-voicemail");
            if (result != TextToSpeech.SUCCESS) throw new IllegalStateException("Android speech request was rejected");
            if (!done.await(60, TimeUnit.SECONDS)) throw new IllegalStateException("Android speech generation timed out");
            if (error.get() != null) throw new IllegalStateException(error.get());
            if (!output.isFile() || output.length() <= 44) throw new IllegalStateException("Android speech produced no audio");
            complete = true;
        } finally {
            engine.stop();
            engine.shutdown();
            if (!complete) output.delete();
        }
    }
}
