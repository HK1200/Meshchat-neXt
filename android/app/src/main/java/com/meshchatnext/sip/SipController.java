package com.meshchatnext.sip;
import android.content.*;
import android.os.*;
import org.json.JSONObject;
/** Messenger IPC: SIP network binding never touches neXt's main process. */
public final class SipController {
    private static SipController instance;
    private final Context context;
    private Messenger service;
    private boolean launchChecked = false;
    private volatile long snapshotVersion;
    public long statusVersion() { return snapshotVersion; }
    private volatile String snapshot = "{\"available\":true,\"state\":\"starting\",\"call_state\":"
        + "\"idle\",\"registered\":false,\"accounts\":[]}";
    private final Messenger reply = new Messenger(new Handler(Looper.getMainLooper(), m -> {
        if (m.what == 2) {
            snapshot = m.getData().getString("json", snapshot);
            snapshotVersion++;
            if (!launchChecked) {
                launchChecked = true;
                try {
                    JSONObject s = new JSONObject(snapshot);
                    if (s.optBoolean("enabled") && "disconnected".equals(s.optString("state"))
                        && !s.optString("selected").isEmpty())
                        send(new JSONObject()
                                 .put("op", "connect")
                                 .put("id", s.getString("selected"))
                                 .toString());
                } catch (Exception ignored) {
                }
            }
        }
        return true;
    }));
    private final ServiceConnection connection = new ServiceConnection() {
        public void onServiceConnected(ComponentName n, IBinder b) {
            service = new Messenger(b);
            send("{\"op\":\"status\"}");
        }
        public void onServiceDisconnected(ComponentName n) {
            service = null;
            snapshot = "{\"available\":true,\"state\":\"disconnected\",\"call_state\":\"idle\","
                + "\"registered\":false,\"accounts\":[]}";
        }
    };
    private SipController(Context c) {
        context = c.getApplicationContext();
        if (!SipPolicy.platformSupported(Build.VERSION.SDK_INT)) {
            snapshot = "{\"available\":false,\"state\":\"unavailable\",\"call_state\":\"idle\",\"registered\":false,\"accounts\":[],\"error\":\"SIP calling requires Android 9 or later\"}";
            return;
        }
        context.bindService(
            new Intent(context, SipService.class), connection, Context.BIND_AUTO_CREATE);
    }
    public static synchronized SipController get(Context c) {
        if (instance == null)
            instance = new SipController(c);
        return instance;
    }
    public String status() {
        if (service != null)
            try {
                Message m = Message.obtain(null, 3);
                m.replyTo = reply;
                service.send(m);
            } catch (RemoteException ignored) {
            }
        return snapshot;
    }
    public synchronized String send(String json) {
        if (!SipPolicy.platformSupported(Build.VERSION.SDK_INT))
            return "{\"ok\":false,\"error\":\"SIP calling requires Android 9 or later\"}";
        if (service == null)
            return "{\"ok\":false,\"error\":\"SIP service is starting; try again\"}";
        try {
            JSONObject req = new JSONObject(json);
            String op = req.optString("op");
            String id = java.util.UUID.randomUUID().toString();
            req.put("request_id", id);
            if ("connect".equals(op)) {
                Intent start = new Intent(context, SipService.class);
                if (Build.VERSION.SDK_INT >= 26)
                    context.startForegroundService(start);
                else
                    context.startService(start);
            }
            Message m = Message.obtain(null, 1);
            Bundle data = new Bundle();
            data.putString("json", req.toString());
            m.setData(data);
            m.replyTo = reply;
            service.send(m);
            return new JSONObject().put("ok", true).put("request_id", id).toString();
        } catch (Exception e) {
            return "{\"ok\":false,\"error\":\"SIP request could not be sent\"}";
        }
    }
}
