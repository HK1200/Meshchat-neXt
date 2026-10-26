package com.meshchatnext.sip;
/** Strict validation before data reaches SIP's parameter-based account parser. */
public final class SipPolicy {
    public static boolean user(String value) {
        return value != null && value.matches("[A-Za-z0-9_.+*-]{1,64}");
    }
    public static boolean host(String value) {
        return value != null && value.length() <= 253
            && value.matches("[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?") && !value.contains("..");
    }
    public static boolean port(int value) {
        return value > 0 && value <= 65535;
    }
    public static String dial(String value, String host, int port) {
        if (value == null || value.length() > 320)
            throw new IllegalArgumentException("Enter a SIP extension or address");
        if (value.matches("[0-9*#+]{1,64}"))
            return "sip:" + value.replace("#", "%23") + "@" + host + ":" + port;
        if (value.matches("(?i)sip:[A-Za-z0-9_.+*%~-]{1,64}@[A-Za-z0-9.-]+(?::[0-9]{1,5})?"))
            return value;
        throw new IllegalArgumentException("Use an extension or sip:user@server address");
    }
    private SipPolicy() {}
}
