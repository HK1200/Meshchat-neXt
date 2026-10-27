package com.meshchatnext;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Set;

final class UpdateInstallPolicy {
    static boolean sessionResultMatches(int expectedId, int actualId, String expectedToken, String actualToken) {
        return expectedId >= 0 && expectedId == actualId && expectedToken != null
            && !expectedToken.isEmpty() && expectedToken.equals(actualToken);
    }
    static boolean verifyInstalledResult(String state, String attempt, String expected,
                                         long before, long after, long currentCode, long targetCode) {
        return "installer_opened".equals(state) && attempt != null && attempt.equals(expected)
            && before > 0 && after > before && currentCode >= targetCode;
    }
    static boolean checksum(String expected, String actual, long size, long written) {
        return expected != null && expected.matches("[0-9a-f]{64}") && size > 0 && size == written
            && actual != null && MessageDigest.isEqual(expected.getBytes(StandardCharsets.US_ASCII), actual.getBytes(StandardCharsets.US_ASCII));
    }
    static boolean packageMatches(String installedPackage, String archivePackage, long current, long target,
                                  Set<String> installedSigners, Set<String> archiveSigners) {
        return installedPackage != null && installedPackage.equals(archivePackage) && target >= current
            && installedSigners != null && !installedSigners.isEmpty() && installedSigners.equals(archiveSigners);
    }
}
