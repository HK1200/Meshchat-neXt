package com.meshchatnext.meshcore;

import com.meshchatnext.radio.DeviceAccess;
import org.junit.Test;
import static org.junit.Assert.*;

public class NativeSessionTest {
    private static final class Session extends NativeSession {
        @Override public void start() { emit("ready", null, "test"); }
        @Override public void send(byte[] data) { emit("data", data, "test"); }
        @Override public void close() { closed = true; }
    }

    @Test public void separateMailboxesAndCloseStates() throws Exception {
        Session meshcore = new Session();
        Session other = new Session();
        meshcore.start();
        other.start();
        meshcore.close();
        assertTrue(meshcore.closed);
        assertFalse(other.closed);
        assertEquals("ready", other.poll(0).kind);
        assertNull(other.poll(0));
    }

    @Test public void mailboxOverflowFailsClosedRatherThanSilentlyDroppingFrames() throws Exception {
        Session session = new Session();
        for (int i = 0; i < 257; i++) session.send(new byte[] {1});
        assertTrue(session.closed);
        assertEquals("receive_queue_overflow", session.poll(0).detail);
    }

    @Test public void differentRadioAddressesCanCoexistAndOnlyOwnerCanRelease() {
        Object rnode = new Object();
        Object meshcore = new Object();
        String first = "AA:BB:CC:DD:EE:01";
        String second = "AA:BB:CC:DD:EE:02";
        try {
            assertTrue(DeviceAccess.claimBle(first, rnode));
            assertTrue(DeviceAccess.claimBle(second, meshcore));
            assertFalse(DeviceAccess.claimBle(first.toLowerCase(), meshcore));
            DeviceAccess.releaseBle(first, meshcore);
            assertFalse(DeviceAccess.claimBle(first, meshcore));
            DeviceAccess.releaseBle(second, meshcore);
            assertFalse(DeviceAccess.claimBle(first, meshcore));
            DeviceAccess.releaseBle(first, rnode);
            assertTrue(DeviceAccess.claimBle(first, meshcore));
        } finally {
            DeviceAccess.releaseBle(first, rnode);
            DeviceAccess.releaseBle(first, meshcore);
            DeviceAccess.releaseBle(second, meshcore);
        }
    }
}
