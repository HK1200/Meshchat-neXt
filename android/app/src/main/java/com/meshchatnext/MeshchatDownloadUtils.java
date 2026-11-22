package com.meshchatnext;

import java.io.File;
import java.io.IOException;
import java.util.UUID;

final class MeshchatDownloadUtils {

    private static final int DOWNLOAD_NOTIFICATION_ID_BASE = 0x60000;
    private static final java.util.concurrent.ConcurrentHashMap<String, Integer> downloadNotificationIds =
        new java.util.concurrent.ConcurrentHashMap<>();
    private static final java.util.concurrent.atomic.AtomicInteger nextDownloadNotificationId =
        new java.util.concurrent.atomic.AtomicInteger(DOWNLOAD_NOTIFICATION_ID_BASE);

    private MeshchatDownloadUtils() {}

    /**
     * Maps a string download id to a stable notification id so progress updates
     * replace each other and the finished state reuses the same slot.
     */
    static int notificationIdFor(String downloadId) {
        String key = downloadId != null ? downloadId : "download";
        return downloadNotificationIds.computeIfAbsent(key, k -> nextDownloadNotificationId.getAndIncrement());
    }

    /**
     * Produces a filename safe for writing into app storage / MediaStore.
     */
    static String sanitizeFileName(String name) {
        if (name == null || name.isEmpty()) {
            return "download.bin";
        }
        int slash = Math.max(name.lastIndexOf('/'), name.lastIndexOf('\\'));
        String base = slash >= 0 ? name.substring(slash + 1) : name;
        if (base.isEmpty()) {
            return "download.bin";
        }
        // Hyphen must be first or last in the class so it is literal, not a range (space..hyphen would include '*').
        base = base.replaceAll("[^A-Za-z0-9._ \\-]+", "_").trim();
        if (base.isEmpty() || base.equals(".") || base.equals("..")) {
            return "download.bin";
        }
        if (base.length() > 120) {
            base = base.substring(0, 120);
        }
        return base;
    }

    /** Reserve a new basename atomically; never reuse an existing download. */
    static File reserveUniqueTarget(File directory, String safe) throws IOException {
        if (directory == null || safe == null || !safe.equals(sanitizeFileName(safe))) {
            throw new IOException("Invalid download filename");
        }
        File root = directory.getCanonicalFile();
        if (!root.isDirectory()) {
            throw new IOException("Download directory is unavailable");
        }
        int dot = safe.lastIndexOf('.');
        String stem = dot > 0 ? safe.substring(0, dot) : safe;
        String extension = dot > 0 ? safe.substring(dot) : "";
        for (int attempt = 0; attempt < 128; attempt++) {
            String name = attempt == 0 ? safe : stem + " ("
                + (attempt < 100 ? Integer.toString(attempt) : UUID.randomUUID().toString())
                + ")" + extension;
            File candidate = new File(root, name).getCanonicalFile();
            if (!root.equals(candidate.getParentFile())) {
                throw new IOException("Download filename escapes its directory");
            }
            if (candidate.createNewFile()) {
                return candidate;
            }
        }
        throw new IOException("Could not reserve a new download filename");
    }

}
