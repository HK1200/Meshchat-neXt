package com.meshchatnext.sip;
import org.junit.Test;
import static org.junit.Assert.*;
public class SipRingbackTest {
    static final class Tone implements SipRingback.Output {
        int starts, stops;
        public void start() { starts++; }
        public void stop() { stops++; }
    }
    @Test public void remoteRingingStartsOnceAndAnswerStops() {
        Tone tone = new Tone(); SipRingback ring = new SipRingback(tone);
        ring.event("calling"); assertEquals(0, tone.starts);
        ring.event("ringing"); ring.event("ringing"); assertEquals(1, tone.starts);
        ring.event("connected"); assertEquals(1, tone.stops);
        ring.event("ringing"); assertEquals(1, tone.starts);
    }
    @Test public void earlyMediaAndIncomingNeverGetLocalRingback() {
        Tone tone = new Tone(); SipRingback ring = new SipRingback(tone);
        ring.event("calling"); ring.event("ringing"); ring.event("progress");
        ring.event("ringing"); assertEquals(1, tone.starts); assertEquals(1, tone.stops);
        ring.event("ended"); ring.event("incoming"); ring.event("ringing");
        assertEquals(1, tone.starts);
        ring.event("calling"); ring.event("ringing"); assertEquals(2, tone.starts);
        ring.stop(); ring.stop(); assertEquals(2, tone.stops);
    }
}
