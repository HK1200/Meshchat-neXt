package com.meshchatnext.sip;

/** Keep full app navigation behind the device lock and tied to the current call. */
public final class SipCallScreenPolicy {
    private SipCallScreenPolicy() { }
    public static boolean active(String token, String current, String state) {
        return token != null && token.matches("[0-9a-f]{32}") && token.equals(current)
            && "connected".equals(state);
    }
    public static boolean canHandoff(String token, String current, String state, boolean locked) {
        return !locked && active(token, current, state);
    }
}
