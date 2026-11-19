package com.meshchatnext.sip;

import static org.junit.Assert.*;
import org.junit.Test;

public class SipCallScreenPolicyTest {
    private static final String TOKEN = "00000000000000000000000000000000";
    private static final String OTHER = "11111111111111111111111111111111";
    @Test public void connectedCallStaysAboveSecureLock() {
        assertTrue(SipCallScreenPolicy.active(TOKEN, TOKEN, "connected"));
        assertFalse(SipCallScreenPolicy.canHandoff(TOKEN, TOKEN, "connected", true));
        assertTrue(SipCallScreenPolicy.canHandoff(TOKEN, TOKEN, "connected", false));
    }
    @Test public void staleCallCannotOpenOrControlReplacement() {
        assertFalse(SipCallScreenPolicy.active(TOKEN, OTHER, "connected"));
        assertFalse(SipCallScreenPolicy.canHandoff(TOKEN, OTHER, "connected", false));
    }
    @Test public void ringingAndEndedCallsNeverHandoff() {
        for (String state : new String[]{"incoming", "calling", "idle", "ended", ""})
            assertFalse(SipCallScreenPolicy.canHandoff(TOKEN, TOKEN, state, false));
    }
    @Test public void malformedTokensNeverAuthorizeControls() {
        for (String token : new String[]{null, "", "short", "0123456789abcdef0123456789abcdeg00"})
            assertFalse(SipCallScreenPolicy.active(token, token, "connected"));
    }
}
