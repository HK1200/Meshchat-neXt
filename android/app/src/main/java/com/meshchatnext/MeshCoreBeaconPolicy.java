package com.meshchatnext;

/** Pure freshness/rate gate, independently testable without requesting GPS. */
final class MeshCoreBeaconPolicy {
    private MeshCoreBeaconPolicy() {}
    static boolean shouldSend(long nowMs, long fixElapsedNanos, float accuracy, long lastMs, int intervalSeconds) {
        long age = nowMs - fixElapsedNanos / 1000000L;
        return age >= 0 && age <= 30000 && !Float.isNaN(accuracy) && !Float.isInfinite(accuracy)
            && accuracy >= 0 && accuracy <= 255
            && (lastMs < 0 || nowMs - lastMs >= intervalSeconds * 1000L);
    }
}
