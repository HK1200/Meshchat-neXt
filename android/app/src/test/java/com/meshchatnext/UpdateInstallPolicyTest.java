package com.meshchatnext;
import org.junit.Test;
import static org.junit.Assert.*;
import java.util.Collections;
public class UpdateInstallPolicyTest {
    private final java.util.Set<String> trusted = Collections.singleton("installed-certificate");
    @Test public void onlySamePackageSignerAndNonDowngradeAreAccepted() {
        assertTrue(UpdateInstallPolicy.packageMatches("next", "next", 3, 4, trusted, trusted));
        assertTrue(UpdateInstallPolicy.packageMatches("next", "next", 3, 3, trusted, trusted));
        assertFalse(UpdateInstallPolicy.packageMatches("next", "other", 3, 4, trusted, trusted));
        assertFalse(UpdateInstallPolicy.packageMatches("next", "next", 3, 2, trusted, trusted));
        assertFalse(UpdateInstallPolicy.packageMatches("next", "next", 3, 4, trusted, Collections.singleton("other-certificate")));
        assertFalse(UpdateInstallPolicy.packageMatches("next", "next", 3, 4, Collections.emptySet(), Collections.emptySet()));
    }
    @Test public void cancelledOrFailedAttemptsCannotReuseOldInstallCompletion() {
        assertTrue(UpdateInstallPolicy.verifyInstalledResult("installer_opened", "new", "new", 10, 20, 3, 3));
        assertFalse(UpdateInstallPolicy.verifyInstalledResult("cancelled", "new", "new", 10, 20, 3, 3));
        assertFalse(UpdateInstallPolicy.verifyInstalledResult("failed", "new", "new", 10, 20, 3, 3));
        assertFalse(UpdateInstallPolicy.verifyInstalledResult("installer_opened", "old", "new", 10, 20, 3, 3));
        assertFalse(UpdateInstallPolicy.verifyInstalledResult("installer_opened", "new", "new", 20, 20, 3, 3));
    }
    @Test public void installerCallbacksMustBelongToCurrentPrivateSession() {
        assertTrue(UpdateInstallPolicy.sessionResultMatches(7, 7, "secret", "secret"));
        assertFalse(UpdateInstallPolicy.sessionResultMatches(7, 8, "secret", "secret"));
        assertFalse(UpdateInstallPolicy.sessionResultMatches(7, 7, "secret", "stale"));
        assertFalse(UpdateInstallPolicy.sessionResultMatches(-1, -1, "", ""));
    }
    @Test public void checksumAndExactSizeAreBothRequired() {
        String hash = String.join("", Collections.nCopies(64, "a"));
        assertTrue(UpdateInstallPolicy.checksum(hash, hash, 100, 100));
        assertFalse(UpdateInstallPolicy.checksum(hash, hash, 100, 99));
        assertFalse(UpdateInstallPolicy.checksum(hash, hash.replace('a', 'b'), 100, 100));
        assertFalse(UpdateInstallPolicy.checksum("not-a-checksum", "not-a-checksum", 100, 100));
    }
}
