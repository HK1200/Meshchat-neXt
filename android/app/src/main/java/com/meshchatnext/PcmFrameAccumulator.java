package com.meshchatnext;

import java.util.Arrays;

/**
 * Accumulates mono PCM16 little-endian microphone data into complete
 * fixed-duration frames.
 *
 * This class has no Android dependencies and is intended to be used
 * by a single microphone capture thread.
 */
final class PcmFrameAccumulator {

    private final int frameBytes;
    private final byte[] pending;
    private int pendingBytes;

    PcmFrameAccumulator(int sampleRate, int frameMs) {
        if (sampleRate <= 0 || frameMs <= 0
                || ((long) sampleRate * frameMs) % 1000 != 0) {
            throw new IllegalArgumentException("Invalid PCM frame configuration");
        }

        long size = ((long) sampleRate * frameMs / 1000) * 2;

        if (size <= 0 || size > Integer.MAX_VALUE) {
            throw new IllegalArgumentException("Invalid PCM frame size");
        }

        frameBytes = (int) size;
        pending = new byte[frameBytes];
    }

    interface FrameConsumer {
        void accept(byte[] frame);
    }

    void append(byte[] data, int length, FrameConsumer consumer) {
        if (data == null || consumer == null
                || length < 0 || length > data.length
                || (length & 1) != 0) {
            throw new IllegalArgumentException("Invalid PCM input");
        }

        int offset = 0;

        while (offset < length) {
            int copy = Math.min(frameBytes - pendingBytes, length - offset);

            System.arraycopy(data, offset, pending, pendingBytes, copy);

            pendingBytes += copy;
            offset += copy;

            if (pendingBytes == frameBytes) {
                consumer.accept(Arrays.copyOf(pending, frameBytes));
                pendingBytes = 0;
            }
        }
    }

    void reset() {
        pendingBytes = 0;
    }

    int getFrameBytes() {
        return frameBytes;
    }
}
