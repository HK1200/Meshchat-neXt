package com.meshchatnext.sip;

import java.util.*;

/** Monotonic cooldowns: callers supply only networks allowed by the account. */
final class SipNetworkRetry<T> {
    private final Map<T, Long> retryAt = new HashMap<>();
    void failed(T network, long now) { if (network != null) retryAt.put(network, now + 60000L); }
    void clear() { retryAt.clear(); }
    T choose(List<T> candidates, T current, boolean registered, long now) {
        retryAt.keySet().retainAll(candidates);
        if (registered && candidates.contains(current)) return current;
        for (T network : candidates) if (now >= retryAt.getOrDefault(network, 0L)) return network;
        return null;
    }
}
