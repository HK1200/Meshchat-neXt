package com.meshchatnext;

import org.junit.Test;
import static org.junit.Assert.*;

public class AppBackgroundNotificationTest {
    @Test public void summarizesConnectivityWithoutAccountCredentials() {
        assertEquals("SIP · Wi-Fi · registered", AppBackgroundNotification.sipLine("Wi-Fi", "registered", "idle"));
        assertEquals("SIP · waiting for network", AppBackgroundNotification.sipLine("", "waiting_for_network", "idle"));
    }
    @Test public void activeCallTakesPrecedenceAndTextIsBounded() {
        assertEquals("SIP · Mobile data · incoming", AppBackgroundNotification.sipLine("Mobile data", "registered", "incoming"));
        assertFalse(AppBackgroundNotification.sipLine("Wi-Fi\ntext", "registering", "idle").contains("\n"));
        assertTrue(AppBackgroundNotification.sipLine(new String(new char[300]).replace('\0', 'x'), "registered", "idle").length() <= 160);
    }
}
