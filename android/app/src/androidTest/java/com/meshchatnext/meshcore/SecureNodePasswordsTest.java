package com.meshchatnext.meshcore;
import android.content.Context;
import androidx.test.platform.app.InstrumentationRegistry;
import org.junit.Test;
import static org.junit.Assert.*;

public class SecureNodePasswordsTest {
    @Test public void credentialsAreEncryptedAndScoped() throws Exception {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        SecureNodePasswords vault = new SecureNodePasswords(context);
        String owner = new String(new char[64]).replace('\0', '1');
        String peer = new String(new char[64]).replace('\0', '2');
        String secret = "instrumentation-test-only";
        try {
            vault.save(owner, peer, "admin", secret);
            assertTrue(vault.has(owner, peer, "admin"));
            assertFalse(vault.has(owner, peer, "member"));
            assertFalse(vault.has(peer, owner, "admin"));
            assertEquals(secret, vault.load(owner, peer, "admin"));
            String key = owner + ":" + peer + ":admin";
            android.content.SharedPreferences prefs = context.getSharedPreferences("meshcore_node_passwords", Context.MODE_PRIVATE);
            String encrypted = prefs.getString(key, "");
            assertFalse(encrypted.contains(secret));
            vault.save(owner, peer, "admin", secret);
            assertNotEquals(encrypted, prefs.getString(key, ""));
            prefs.edit().putString(key, "1:AAAA:AAAA").commit();
            try { vault.load(owner, peer, "admin"); fail("Tampering must fail"); } catch (Exception expected) { }
        } finally { vault.forget(owner, peer, "admin"); }
        assertFalse(vault.has(owner, peer, "admin"));
    }
}
