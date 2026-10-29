package com.meshchatnext.sip;
import java.util.*;
import org.junit.Test;
import static org.junit.Assert.*;
public class SipNetworkRetryTest {
    @Test public void blockedWifiFallsBackToMobileAndKeepsSuccessfulMobile() {
        SipNetworkRetry<String> p = new SipNetworkRetry<>();
        List<String> both = Arrays.asList("wifi", "mobile");
        assertEquals("wifi", p.choose(both, null, false, 0));
        p.failed("wifi", 100);
        assertEquals("mobile", p.choose(both, null, false, 100));
        assertEquals("mobile", p.choose(both, "mobile", true, 90000));
    }
    @Test public void allFailedNetworksWaitThenBecomeEligibleAgain() {
        SipNetworkRetry<String> p = new SipNetworkRetry<>();
        List<String> both = Arrays.asList("wifi", "mobile");
        p.failed("wifi", 0); p.failed("mobile", 1000);
        assertNull(p.choose(both, null, false, 30000));
        assertEquals("wifi", p.choose(both, null, false, 60000));
    }
    @Test public void neverChoosesNetworkOutsideAllowedCandidates() {
        SipNetworkRetry<String> p = new SipNetworkRetry<>();
        p.failed("wifi", 0);
        assertNull(p.choose(Arrays.asList("wifi"), "mobile", true, 1));
        assertNull(p.choose(Collections.emptyList(), null, false, 2));
        p.clear();
        assertEquals("wifi", p.choose(Arrays.asList("wifi"), null, false, 3));
    }
}
