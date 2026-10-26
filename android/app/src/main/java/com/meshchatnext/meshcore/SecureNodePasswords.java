package com.meshchatnext.meshcore;

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

/** Device-local passwords. No plaintext credentials enter preferences or backups. */
public final class SecureNodePasswords {
    private static final String ALIAS = "meshchat-next-node-passwords-v1";
    private final SharedPreferences prefs;
    private final String application;
    public SecureNodePasswords(Context context) {
        Context app = context.getApplicationContext();
        application = app.getPackageName();
        prefs = app.getSharedPreferences("meshcore_node_passwords", Context.MODE_PRIVATE);
    }
    private String slot(String owner, String peer, String role) {
        if (owner == null || peer == null || !owner.matches("[0-9a-f]{64}") ||
            !peer.matches("[0-9a-f]{64}") || !("admin".equals(role) || "member".equals(role)))
            throw new IllegalArgumentException("Invalid credential slot");
        return owner + ":" + peer + ":" + role;
    }
    private synchronized SecretKey key() throws Exception {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore");
        store.load(null);
        if (!store.containsAlias(ALIAS)) {
            KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
            generator.init(new KeyGenParameterSpec.Builder(ALIAS,
                KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256).build());
            generator.generateKey();
        }
        return (SecretKey) store.getKey(ALIAS, null);
    }
    public boolean has(String owner, String peer, String role) {
        return prefs.contains(slot(owner, peer, role));
    }
    public synchronized void save(String owner, String peer, String role, String password) throws Exception {
        String name = slot(owner, peer, role);
        if (password == null || password.indexOf(0) >= 0 || password.getBytes(StandardCharsets.UTF_8).length > 64)
            throw new IllegalArgumentException("Invalid password");
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key());
        cipher.updateAAD((application + ":" + name).getBytes(StandardCharsets.UTF_8));
        byte[] encrypted = cipher.doFinal(password.getBytes(StandardCharsets.UTF_8));
        String value = "1:" + Base64.encodeToString(cipher.getIV(), Base64.NO_WRAP) + ":" +
            Base64.encodeToString(encrypted, Base64.NO_WRAP);
        if (!prefs.edit().putString(name, value).commit()) throw new IllegalStateException("Credential save failed");
    }
    public synchronized String load(String owner, String peer, String role) throws Exception {
        String name = slot(owner, peer, role);
        String value = prefs.getString(name, null);
        if (value == null) throw new IllegalStateException("No saved password");
        String[] parts = value.split(":", -1);
        if (parts.length != 3 || !"1".equals(parts[0])) throw new IllegalStateException("Invalid saved password");
        byte[] iv = Base64.decode(parts[1], Base64.NO_WRAP);
        if (iv.length != 12) throw new IllegalStateException("Invalid saved password");
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key(), new GCMParameterSpec(128, iv));
        cipher.updateAAD((application + ":" + name).getBytes(StandardCharsets.UTF_8));
        return new String(cipher.doFinal(Base64.decode(parts[2], Base64.NO_WRAP)), StandardCharsets.UTF_8);
    }
    public void forget(String owner, String peer, String role) {
        if (!prefs.edit().remove(slot(owner, peer, role)).commit()) throw new IllegalStateException("Credential removal failed");
    }
}
