package com.meshchatnext.sip;

/** Local ringback only after remote ringing; early media always takes precedence. */
final class SipRingback {
    interface Output { void start(); void stop(); }
    private final Output output;
    private boolean outgoing, earlyMedia, playing;
    SipRingback(Output output) { this.output = output; }
    void event(String state) {
        switch (state) {
            case "calling": stop(); outgoing = true; earlyMedia = false; break;
            case "ringing":
                if (outgoing && !earlyMedia && !playing) { output.start(); playing = true; }
                break;
            case "progress": earlyMedia = true; stop(); break;
            case "incoming":
            case "connected":
            case "ended":
            case "engine_failed": outgoing = false; stop(); break;
            default: break;
        }
    }
    void stop() { if (playing) output.stop(); playing = false; }
}
