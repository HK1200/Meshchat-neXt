package com.meshchatnext.sip;
import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
final class SipVault {
    private static final String ALIAS = "meshchat-next-sip-credentials-v1";
    private final SharedPreferences prefs;
    private final String app;
    SipVault(Context context) {
        prefs = context.getSharedPreferences("sip_secrets", 0);
        app = context.getPackageName();
    }
    private SecretKey key() throws Exception {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore");
        store.load(null);
        if (!store.containsAlias(ALIAS)) {
            KeyGenerator gen = KeyGenerator.getInstance("AES", "AndroidKeyStore");
            gen.init(
                new KeyGenParameterSpec
                    .Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                    .setBlockModes("GCM")
                    .setEncryptionPaddings("NoPadding")
                    .setKeySize(256)
                    .build());
            gen.generateKey();
        }
        return (SecretKey) store.getKey(ALIAS, null);
    }
    void save(String id, String secret) throws Exception {
        Cipher c = Cipher.getInstance("AES/GCM/NoPadding");
        c.init(Cipher.ENCRYPT_MODE, key());
        c.updateAAD((app + ":" + id).getBytes(StandardCharsets.UTF_8));
        String value = Base64.encodeToString(c.getIV(), Base64.NO_WRAP) + ":"
            + Base64.encodeToString(
                c.doFinal(secret.getBytes(StandardCharsets.UTF_8)), Base64.NO_WRAP);
        if (!prefs.edit().putString(id, value).commit())
            throw new IllegalStateException("Password could not be saved");
    }
    String load(String id) throws Exception {
        String v = prefs.getString(id, null);
        if (v == null)
            return null;
        String[] pieces = v.split(":");
        Cipher c = Cipher.getInstance("AES/GCM/NoPadding");
        c.init(Cipher.DECRYPT_MODE, key(),
            new GCMParameterSpec(128, Base64.decode(pieces[0], Base64.NO_WRAP)));
        c.updateAAD((app + ":" + id).getBytes(StandardCharsets.UTF_8));
        return new String(
            c.doFinal(Base64.decode(pieces[1], Base64.NO_WRAP)), StandardCharsets.UTF_8);
    }
    boolean has(String id) {
        return prefs.contains(id);
    }
    void remove(String id) {
        if (!prefs.edit().remove(id).commit())
            throw new IllegalStateException("Password could not be removed");
    }
}
