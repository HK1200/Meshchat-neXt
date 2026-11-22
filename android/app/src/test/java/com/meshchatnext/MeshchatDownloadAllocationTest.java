package com.meshchatnext;

import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import org.junit.Assert;
import org.junit.Assume;
import org.junit.Rule;
import org.junit.Test;
import org.junit.rules.TemporaryFolder;

public class MeshchatDownloadAllocationTest {
    @Rule public TemporaryFolder temporary = new TemporaryFolder();

    @Test public void collisionsNeverOverwriteTheOriginalAfterOneHundredNames() throws Exception {
        File root = temporary.newFolder();
        byte[] existing = "existing fixture".getBytes(StandardCharsets.UTF_8);
        for (int i = 0; i < 100; i++) {
            String name = i == 0 ? "photo.jpg" : "photo (" + i + ").jpg";
            Files.write(new File(root, name).toPath(), existing);
        }
        File result = MeshchatDownloadUtils.reserveUniqueTarget(root, "photo.jpg");
        Assert.assertEquals(root.getCanonicalFile(), result.getParentFile());
        Assert.assertTrue(result.getName().endsWith(".jpg"));
        Assert.assertEquals(0, result.length());
        Assert.assertEquals(101, root.list().length);
        for (File file : root.listFiles()) {
            if (!file.getCanonicalFile().equals(result)) Assert.assertArrayEquals(existing, Files.readAllBytes(file.toPath()));
        }
    }

    @Test public void concurrentDownloadsReserveDifferentFiles() throws Exception {
        File root = temporary.newFolder();
        ExecutorService workers = Executors.newFixedThreadPool(8);
        try {
            List<Future<File>> futures = new ArrayList<>();
            for (int i = 0; i < 32; i++) {
                futures.add(workers.submit(() -> MeshchatDownloadUtils.reserveUniqueTarget(root, "message.txt")));
            }
            Set<File> unique = new HashSet<>();
            for (Future<File> future : futures) {
                File file = future.get();
                Assert.assertTrue(file.isFile());
                Assert.assertTrue(unique.add(file));
            }
            Assert.assertEquals(32, unique.size());
        } finally { workers.shutdownNow(); }
    }

    @Test public void traversalAndSpecialNamesCannotEscapeTheDownloadFolder() throws Exception {
        File root = temporary.newFolder();
        for (String name : new String[] {"../outside", "a/b", "a\\b", ".", "..", ""}) {
            try {
                MeshchatDownloadUtils.reserveUniqueTarget(root, name);
                Assert.fail("Unsafe basename accepted: " + name);
            } catch (IOException expected) { }
        }
        Assert.assertEquals(0, root.list().length);
        Assert.assertEquals("download.bin", MeshchatDownloadUtils.sanitizeFileName(".."));
        Assert.assertEquals("download.bin", MeshchatDownloadUtils.sanitizeFileName("."));
    }

    @Test public void anExistingSymlinkCannotRedirectTheWrite() throws Exception {
        Assume.assumeFalse(System.getProperty("os.name").toLowerCase().contains("win"));
        File root = temporary.newFolder();
        File outside = temporary.newFile();
        byte[] existing = "outside fixture".getBytes(StandardCharsets.UTF_8);
        Files.write(outside.toPath(), existing);
        Files.createSymbolicLink(new File(root, "message.txt").toPath(), outside.toPath());
        try {
            MeshchatDownloadUtils.reserveUniqueTarget(root, "message.txt");
            Assert.fail("Symlink escape accepted");
        } catch (IOException expected) { }
        Assert.assertArrayEquals(existing, Files.readAllBytes(outside.toPath()));
    }
}
