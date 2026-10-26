package com.meshchatnext;

import org.junit.Test;
import static org.junit.Assert.*;

public class MeshCoreBeaconPolicyTest {
    @Test public void onlyCurrentAccurateFixesPass() {
        assertTrue(MeshCoreBeaconPolicy.shouldSend(100000, 99000000000L, 5, -1, 300));
        assertFalse(MeshCoreBeaconPolicy.shouldSend(100000, 60000000000L, 5, -1, 300));
        assertFalse(MeshCoreBeaconPolicy.shouldSend(100000, 101000000000L, 5, -1, 300));
        assertFalse(MeshCoreBeaconPolicy.shouldSend(100000, 99000000000L, 300, -1, 300));
        assertFalse(MeshCoreBeaconPolicy.shouldSend(100000, 99000000000L, Float.NaN, -1, 300));
    }
    @Test public void limitsFrequencyUsingMonotonicTime() {
        assertFalse(MeshCoreBeaconPolicy.shouldSend(100000, 99000000000L, 5, 90000, 60));
        assertTrue(MeshCoreBeaconPolicy.shouldSend(150000, 149000000000L, 5, 90000, 60));
    }
}
