package com.meshchatnext.sip;
import static org.junit.Assert.*;

import org.junit.Test;
public class SipPolicyTest {
    @Test
    public void preventsAccountParameterInjection() {
        assertTrue(SipPolicy.user("test_user"));
        assertFalse(SipPolicy.user("test;auth_pass=other"));
        assertFalse(SipPolicy.host("host\nsip_listen 0.0.0.0"));
        assertFalse(SipPolicy.host("pbx..example"));
        assertFalse(SipPolicy.port(0));
        assertFalse(SipPolicy.port(65536));
        assertTrue(SipPolicy.port(5160));
    }
    @Test
    public void extensionUsesChosenServerAndEncodesHash() {
        assertEquals("sip:*97%23@pbx.example:5160", SipPolicy.dial("*97#", "pbx.example", 5160));
        assertEquals("sip:user@other.example:5060",
            SipPolicy.dial("sip:user@other.example:5060", "pbx.example", 5160));
    }
    @Test
    public void rejectsSipHeaderAndUriInjection() {
        for (String input : new String[] {"sip:a@host?Subject=spoof", "sip:a@host;transport=tcp",
                 "a\r\nTo: b", "https://host", ""}) {
            try {
                SipPolicy.dial(input, "pbx.example", 5160);
                fail(input);
            } catch (IllegalArgumentException expected) {
            }
        }
    }
}
