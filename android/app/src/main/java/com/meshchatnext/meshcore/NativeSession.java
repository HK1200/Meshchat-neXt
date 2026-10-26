package com.meshchatnext.meshcore;

import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.TimeUnit;

/** Per-connection bounded event mailbox. No Python callbacks run on Android binder threads. */
public abstract class NativeSession {
    public static final class Event {
        public final String kind;
        public final byte[] data;
        public final String detail;
        Event(String kind, byte[] data, String detail) {
            this.kind = kind;
            this.data = data;
            this.detail = detail;
        }
    }

    private final ArrayBlockingQueue<Event> events = new ArrayBlockingQueue<>(256);
    protected volatile boolean closed;

    public final Event poll(int timeoutMs) throws InterruptedException {
        return events.poll(Math.min(Math.max(timeoutMs, 0), 1000), TimeUnit.MILLISECONDS);
    }

    protected final void emit(String kind, byte[] data, String detail) {
        if (!events.offer(new Event(kind, data, detail))) {
            events.clear();
            events.offer(new Event("error", null, "receive_queue_overflow"));
            close();
        }
    }

    public abstract void start();
    public abstract void send(byte[] data);
    public abstract void close();
}
