package com.meshchatnext.meshcore;

import android.content.Context;
import android.os.Bundle;
import androidx.test.platform.app.InstrumentationRegistry;
import com.chaquo.python.Python;
import com.chaquo.python.PyObject;
import org.junit.Test;
import static org.junit.Assert.*;
import static org.junit.Assume.*;

/** Explicitly selected hardware only. Same-process tests require an explicitly released RNode. */
public class MeshCoreRadioTest {
    @Test public void backgroundPrepare() {
        Bundle arguments = InstrumentationRegistry.getArguments();
        assumeTrue("true".equals(arguments.getString("meshcoreProcessTest", "false")));
        String target = arguments.getString("meshcoreTarget", "");
        assumeTrue(!target.isEmpty());
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        Python.getInstance().getModule("meshcore_background_checks").callAttr("prepare", context, target);
    }

    @Test public void backgroundResume() throws Exception {
        Bundle arguments = InstrumentationRegistry.getArguments();
        assumeTrue("true".equals(arguments.getString("meshcoreProcessTest", "false")));
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        String result = Python.getInstance().getModule("meshcore_background_checks")
            .callAttr("resume", context).toString();
        assertEquals("ok", new org.json.JSONObject(result).getString("status"));
        android.util.Log.i("MeshCoreBackgroundTest", result);
    }

    @Test public void identityAndRecovery() throws Exception {
        Bundle arguments = InstrumentationRegistry.getArguments();
        assumeTrue("true".equals(arguments.getString("meshcoreIdentityWrite", "false")));
        String target = arguments.getString("meshcoreTarget", "");
        assumeTrue(!target.isEmpty());
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        String result = Python.getInstance().getModule("meshcore_service_checks")
            .callAttr("probe", context, target).toString();
        assertEquals("ok", new org.json.JSONObject(result).getString("status"));
        android.util.Log.i("MeshCoreServiceTest", result);
    }

    @Test public void channelRoundTrip() throws Exception {
        Bundle arguments = InstrumentationRegistry.getArguments();
        assumeTrue("true".equals(arguments.getString("meshcoreChannelWrite", "false")));
        String target = arguments.getString("meshcoreTarget", "");
        String peer = arguments.getString("meshcorePeerTarget", "");
        assumeTrue(!target.isEmpty() && !peer.isEmpty());
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        String result = Python.getInstance().getModule("meshcore_channel_checks")
            .callAttr("round_trip", context, target, peer).toString();
        org.json.JSONObject report = new org.json.JSONObject(result);
        assertEquals("ok", report.getString("status"));
        assertTrue(report.getBoolean("public_round_trip"));
        assertTrue(report.getBoolean("private_round_trip"));
        assertTrue(report.getBoolean("channels_restored"));
        android.util.Log.i("MeshCoreChannelsTest", result);
    }

    @Test public void directMessaging() throws Exception {
        Bundle arguments = InstrumentationRegistry.getArguments();
        String target = arguments.getString("meshcoreTarget", "");
        String peer = arguments.getString("meshcorePeer", "");
        assumeTrue(!target.isEmpty() && !peer.isEmpty());
        boolean send = "true".equals(arguments.getString("meshcoreMessageWrite", "false"));
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        String result = Python.getInstance().getModule("meshcore_runtime_checks")
            .callAttr("messaging", context, target, peer, 90, send).toString();
        org.json.JSONObject report = new org.json.JSONObject(result);
        assertEquals("ok", report.getString("status"));
        assertTrue(report.getBoolean("test_peer_found"));
        assertTrue(report.getBoolean("settings_unchanged"));
        android.util.Log.i("MeshCoreMessagingTest", result);
        if (send) {
            assertTrue("Radio did not confirm delivery", report.getBoolean("delivered"));
            assertTrue("No test peer reply received", report.getBoolean("received"));
            assertTrue(report.getBoolean("history_persisted"));
        }
    }

    @Test public void sameProcessRadios() throws Exception {
        Bundle arguments = InstrumentationRegistry.getArguments();
        assumeTrue("true".equals(arguments.getString("meshcoreSameProcess", "false")));
        String target = arguments.getString("meshcoreTarget", "");
        String rnode = arguments.getString("rnodeTarget", "");
        assumeTrue(!target.isEmpty() && !rnode.isEmpty());
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        String result = Python.getInstance().getModule("meshcore_runtime_checks")
            .callAttr("same_process", context, target, rnode).toString();
        assertEquals("ok", new org.json.JSONObject(result).getString("status"));
        android.util.Log.i("MeshCoreSameProcessTest", result);
    }

    @Test public void radioDiscovery() {
        Bundle arguments = InstrumentationRegistry.getArguments();
        assumeTrue("true".equals(arguments.getString("meshcoreDiscovery", "false")));
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        String result = Python.getInstance().getModule("meshcore_runtime_checks")
            .callAttr("discover", context).toString();
        android.util.Log.i("MeshCoreDiscoveryTest", result);
    }

    @Test public void coexistenceReadOnly() throws Exception {
        Bundle arguments = InstrumentationRegistry.getArguments();
        assumeTrue("true".equals(arguments.getString("meshcoreCoexistence", "false")));
        String target = arguments.getString("meshcoreTarget", "");
        assumeTrue(!target.isEmpty());
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        String result = Python.getInstance().getModule("meshcore_runtime_checks")
            .callAttr("coexist", context, target, 20).toString();
        assertEquals("ok", new org.json.JSONObject(result).getString("status"));
        android.util.Log.i("MeshCoreCoexistenceTest", result);
    }

    @Test public void radioSettingsRoundTrip() {
        Bundle arguments = InstrumentationRegistry.getArguments();
        assumeTrue("Settings writes require explicit test opt-in",
            "true".equals(arguments.getString("meshcoreSettingsWrite", "false")));
        String kind = arguments.getString("meshcoreTransport", "");
        String target = arguments.getString("meshcoreTarget", "");
        assumeTrue(!kind.isEmpty() && !target.isEmpty());
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        Python python = Python.getInstance();
        PyObject coroutine = python.getModule("meshchatnext.src.backend.meshcore_session")
            .callAttr("probe_radio_settings", kind, target, new com.chaquo.python.Kwarg("context", context));
        PyObject result = python.getModule("asyncio").callAttr("run", coroutine);
        assertEquals("ok", result.callAttr("__getitem__", "settings").toString());
        assertEquals("ok", result.callAttr("__getitem__", "restored").toString());
        android.util.Log.i("MeshCoreSettingsTest", result.toString());
    }

    @Test public void companionHandshake() {
        Bundle arguments = InstrumentationRegistry.getArguments();
        String kind = arguments.getString("meshcoreTransport", "");
        String target = arguments.getString("meshcoreTarget", "");
        assumeTrue("Requires explicit MeshCore radio arguments", !kind.isEmpty() && !target.isEmpty());
        assertTrue(kind.equals("usb") || kind.equals("ble"));
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        Python python = Python.getInstance();
        PyObject module = python.getModule("meshchatnext.src.backend.meshcore_transport");
        PyObject coroutine = module.callAttr("probe_radio", kind, target,
            new com.chaquo.python.Kwarg("context", context));
        PyObject result = python.getModule("asyncio").callAttr("run", coroutine);
        assertEquals("ok", result.callAttr("__getitem__", "handshake").toString());
        assertEquals("ok", result.callAttr("__getitem__", "query").toString());
    }

    @Test public void managedProtocolSession() {
        Bundle arguments = InstrumentationRegistry.getArguments();
        String kind = arguments.getString("meshcoreTransport", "");
        String target = arguments.getString("meshcoreTarget", "");
        assumeTrue("Requires explicit MeshCore radio arguments", !kind.isEmpty() && !target.isEmpty());
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        Python python = Python.getInstance();
        PyObject module = python.getModule("meshchatnext.src.backend.meshcore_session");
        PyObject coroutine = module.callAttr("probe_managed_session", kind, target,
            new com.chaquo.python.Kwarg("context", context));
        PyObject result = python.getModule("asyncio").callAttr("run", coroutine);
        assertEquals("ok", result.callAttr("__getitem__", "protocol").toString());
        assertEquals("ok", result.callAttr("__getitem__", "reconnect").toString());
        assertEquals("ok", result.callAttr("__getitem__", "cleanup").toString());
    }
}
