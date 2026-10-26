package com.meshchatnext.sip;
/** All engine operations execute in the isolated SIP service process. */
public final class SipEngine {
    static {
        System.loadLibrary("next_sip");
    }
    public static native int run(SipService listener, String user, String host, int port,
        String password, String networkConfig);
    public static native void command(int operation, String value);
    private SipEngine() {}
}
