package com.meshchatnext.sip;

import android.Manifest;
import android.app.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.content.pm.ServiceInfo;
import android.media.*;
import android.net.*;
import android.os.*;
import com.meshchatnext.MainActivity;
import com.meshchatnext.R;
import java.util.*;
import java.util.concurrent.*;
import org.json.*;

/** Dedicated process: DNS, SIP and RTP are bound together to an allowed network. */
public final class SipService extends Service {
    private static final int NOTIFICATION = 6400, INCOMING = 6401;
    private final Handler main = new Handler(Looper.getMainLooper());
    private final ExecutorService work = Executors.newSingleThreadExecutor();
    private final List<Messenger> listeners = new ArrayList<>();
    private final Map<String, String> sessionPasswords = new HashMap<>();
    private SharedPreferences preferences;
    private SipVault vault;
    private JSONArray accounts;
    private JSONObject active;
    private JSONObject quality = new JSONObject();
    public void onCallStats(String json) {
        long emitted = generation;
        work.execute(() -> {
            if (stopping || emitted != generation)
                return;
            try {
                quality = new JSONObject(json);
                publish();
            } catch (JSONException ignored) {
            }
        });
    }
    private volatile String state = "disconnected", callState = "idle", peer = "", error = "",
                            networkName = "";
    private volatile String selected = "", lastRequest = "", requestError = "";
    private boolean desired = false, speaker = false, muted = false;
    private volatile boolean registered = false;
    private Network bound;
    private boolean cellularRequested = false;
    private final ConnectivityManager.NetworkCallback cellular =
        new ConnectivityManager.NetworkCallback() {
            @Override
            public void onAvailable(Network n) {
                work.execute(() -> reconcile());
            }
            @Override
            public void onLost(Network n) {
                work.execute(() -> reconcile());
            }
        };
    private Thread engine;
    private volatile boolean stopping = false;
    private volatile long generation = 0;
    private int recoveryDelay = 1000;
    private AudioManager audio;
    private AudioFocusRequest focus;
    private android.media.audiofx.AcousticEchoCanceler echo;
    private android.media.audiofx.NoiseSuppressor noise;
    public void onAudioSession(int id) {
        main.post(() -> {
            if (echo != null) {
                echo.release();
                echo = null;
            }
            if (noise != null) {
                noise.release();
                noise = null;
            }
            if (id <= 0)
                return;
            try {
                if (android.media.audiofx.AcousticEchoCanceler.isAvailable()) {
                    echo = android.media.audiofx.AcousticEchoCanceler.create(id);
                    if (echo != null)
                        echo.setEnabled(true);
                }
                if (android.media.audiofx.NoiseSuppressor.isAvailable()) {
                    noise = android.media.audiofx.NoiseSuppressor.create(id);
                    if (noise != null)
                        noise.setEnabled(true);
                }
            } catch (RuntimeException ignored) {
            }
        });
    }

    private ConnectivityManager connectivity;
    private final Messenger messenger = new Messenger(new Handler(Looper.getMainLooper(), m -> {
        if (m.what == 3) {
            work.execute(() -> publish());
            return true;
        }
        if (m.what != 1)
            return false;
        if (m.replyTo != null && !listeners.contains(m.replyTo))
            listeners.add(m.replyTo);
        String json = m.getData().getString("json", "{}");
        work.execute(() -> {
            try {
                JSONObject req = new JSONObject(json);
                lastRequest = req.optString("request_id");
                requestError = "";
                command(req);
            } catch (Exception e) {
                error = e instanceof IllegalArgumentException
                    ? e.getMessage()
                    : "SIP operation failed; check the account settings";
                requestError = error;
                publish();
            }
        });
        return true;
    }));
    private final ConnectivityManager.NetworkCallback callback =
        new ConnectivityManager.NetworkCallback() {
            @Override
            public void onAvailable(Network n) {
                work.execute(() -> reconcile());
            }
            @Override
            public void onLost(Network n) {
                work.execute(() -> reconcile());
            }
            @Override
            public void onCapabilitiesChanged(Network n, NetworkCapabilities c) {
                work.execute(() -> reconcile());
            }
        };
    @Override
    public void onCreate() {
        super.onCreate();
        preferences = getSharedPreferences("sip_accounts", 0);
        vault = new SipVault(this);
        try {
            accounts = new JSONArray(preferences.getString("accounts", "[]"));
        } catch (Exception e) {
            accounts = new JSONArray();
        }
        selected = preferences.getString("selected", "");
        // Remove calling accounts registered by the earlier local dialer preview.
        // This only addresses our own component and does not inspect other accounts.
        try {
            android.telecom.TelecomManager telecom = getSystemService(android.telecom.TelecomManager.class);
            for (int i = 0; i < accounts.length(); i++) {
                telecom.unregisterPhoneAccount(new android.telecom.PhoneAccountHandle(
                    new ComponentName(getPackageName(), "com.meshchatnext.sip.SipTelecomService"),
                    accounts.getJSONObject(i).getString("id")));
            }
        } catch (Exception ignored) { }
        connectivity = (ConnectivityManager) getSystemService(CONNECTIVITY_SERVICE);
        audio = (AudioManager) getSystemService(AUDIO_SERVICE);
        NotificationManager nm = getSystemService(NotificationManager.class);
        nm.createNotificationChannel(new NotificationChannel(
            "sip_service", "SIP connection", NotificationManager.IMPORTANCE_LOW));
        NotificationChannel calls = new NotificationChannel(
            "sip_calls", "SIP incoming calls", NotificationManager.IMPORTANCE_HIGH);
        calls.setSound(RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE),
            new AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_NOTIFICATION_RINGTONE)
                .build());
        nm.createNotificationChannel(calls);
        connectivity.registerNetworkCallback(
            new NetworkRequest.Builder()
                .addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                .build(),
            callback);
    }
    @Override
    public IBinder onBind(Intent intent) {
        return messenger.getBinder();
    }
    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        foreground(false);
        if (intent != null && "hangup".equals(intent.getAction()))
            work.execute(() -> { SipEngine.command(3, ""); });
        if (intent == null && preferences.getBoolean("enabled", false))
            work.execute(() -> {
                try {
                    selected = preferences.getString("selected", "");
                    active = find(selected);
                    String secret = vault.load(selected);
                    if (secret == null) {
                        state = "password_required";
                        publish();
                        stopForeground(STOP_FOREGROUND_REMOVE);
                        stopSelf();
                        return;
                    }
                    sessionPasswords.put(selected, secret);
                    desired = true;
                    requestCellular();
                    reconcile();
                } catch (Exception e) {
                    state = "disconnected";
                    publish();
                    stopForeground(STOP_FOREGROUND_REMOVE);
                    stopSelf();
                }
            });
        return preferences.getBoolean("enabled", false) ? START_STICKY : START_NOT_STICKY;
    }
    private PendingIntent open() {
        Intent i = new Intent(this, MainActivity.class);
        i.setAction(Intent.ACTION_VIEW);
        i.setData(Uri.parse("meshchatnext://app/call?network=sip"));
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        return PendingIntent.getActivity(
            this, 6400, i, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }
    private void foreground(boolean microphone) {
        Notification n = new Notification.Builder(this, "sip_service")
                             .setSmallIcon(R.drawable.ic_stat_meshchatnext)
                             .setContentTitle(active == null ? "SIP"
                                                             : "SIP · "
                                         + active.optString("label", active.optString("extension")))
                             .setContentText(networkName.isEmpty() ? "SIP account connection"
                                                                   : networkName + " · " + state)
                             .setContentIntent(open())
                             .setOngoing(true)
                             .build();
        if (Build.VERSION.SDK_INT >= 29)
            startForeground(NOTIFICATION, n,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_PHONE_CALL
                    | (microphone ? ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE : 0));
        else
            startForeground(NOTIFICATION, n);
    }
    private JSONObject find(String id) throws JSONException {
        for (int i = 0; i < accounts.length(); i++)
            if (id.equals(accounts.getJSONObject(i).optString("id")))
                return accounts.getJSONObject(i);
        throw new IllegalArgumentException("Select a SIP account");
    }
    private void persist() {
        if (!preferences.edit()
                 .putString("accounts", accounts.toString())
                 .putString("selected", selected)
                 .commit())
            throw new IllegalStateException("Account save failed");
    }
    private void command(JSONObject req) throws Exception {
        String op = req.optString("op");
        error = "";
        switch (op) {
            case "status":
                break;
            case "save": {
                JSONObject input = req.getJSONObject("account");
                String id = input.optString("id");
                boolean editing = !id.isEmpty();
                if (editing)
                    find(id);
                else
                    id = UUID.randomUUID().toString();
                String user = input.optString("extension").trim(),
                       host = input.optString("host", "premium.hamsoverip.com").trim();
                int port = input.optInt("port", 5160);
                if (!SipPolicy.user(user) || !SipPolicy.host(host) || !SipPolicy.port(port))
                    throw new IllegalArgumentException("Check the extension, server and port");
                String mode = input.optString("network", "wifi_mobile");
                JSONArray allowed = input.optJSONArray("allowed_networks");
                if (allowed != null) {
                    boolean wifi = false, mobile = false;
                    for (int i = 0; i < allowed.length(); i++) {
                        String item = allowed.optString(i);
                        if ("wifi".equals(item))
                            wifi = true;
                        else if ("mobile".equals(item))
                            mobile = true;
                        else
                            throw new IllegalArgumentException(
                                "No compatible I2P SIP route is available");
                    }
                    if (!wifi && !mobile)
                        throw new IllegalArgumentException(
                            "Select at least one allowed SIP network");
                    mode = wifi ? (mobile ? "wifi_mobile" : "wifi") : "mobile";
                }
                if (!Arrays.asList("wifi", "mobile", "wifi_mobile").contains(mode))
                    throw new IllegalArgumentException("No compatible I2P SIP route is available");
                JSONArray networks = new JSONArray();
                if (!"mobile".equals(mode))
                    networks.put("wifi");
                if (!"wifi".equals(mode))
                    networks.put("mobile");
                boolean save = input.optBoolean("save_password", true);
                String password = req.optString("password", "");
                if (password.indexOf(0) >= 0 || password.length() > 256)
                    throw new IllegalArgumentException("Invalid password");
                if (password.isEmpty() && editing) {
                    password = sessionPasswords.get(id);
                    if (password == null)
                        password = vault.load(id);
                }
                if (password == null || password.isEmpty())
                    throw new IllegalArgumentException("Enter the account password");
                if (save)
                    vault.save(id, password);
                else
                    vault.remove(id);
                sessionPasswords.put(id, password);
                JSONObject account =
                    new JSONObject()
                        .put("id", id)
                        .put("label",
                            input.optString("label", user)
                                .substring(
                                    0, Math.min(80, input.optString("label", user).length())))
                        .put("extension", user)
                        .put("host", host)
                        .put("port", port)
                        .put("network", mode)
                        .put("allowed_networks", networks)
                        .put("save_password", save);
                JSONArray next = new JSONArray();
                for (int i = 0; i < accounts.length(); i++)
                    if (!accounts.getJSONObject(i).optString("id").equals(id))
                        next.put(accounts.getJSONObject(i));
                next.put(account);
                accounts = next;
                if (selected.isEmpty())
                    selected = id;
                persist();
                if (desired && selected.equals(id)) {
                    stopEngine();
                    active = account;
                    requestCellular();
                    reconcile();
                }
                break;
            }
            case "remove": {
                String id = req.getString("id");
                find(id);
                if (id.equals(selected)) {
                    desired = false;
                    stopEngine();
                    selected = "";
                    active = null;
                    state = "disconnected";
                    stopForeground(STOP_FOREGROUND_REMOVE);
                }
                vault.remove(id);
                sessionPasswords.remove(id);
                if (id.equals(preferences.getString("selected", ""))) {
                    preferences.edit().putBoolean("enabled", false).commit();
                    releaseCellular();
                    stopSelf();
                }
                JSONArray next = new JSONArray();
                for (int i = 0; i < accounts.length(); i++)
                    if (!accounts.getJSONObject(i).optString("id").equals(id))
                        next.put(accounts.getJSONObject(i));
                accounts = next;
                persist();
                break;
            }
            case "connect": {
                if (Build.VERSION.SDK_INT < 28)
                    throw new IllegalArgumentException("SIP calling requires Android 9 or later");
                if (!"idle".equals(callState))
                    throw new IllegalArgumentException("End the current SIP call first");
                desired = false;
                stopEngine();
                selected = req.getString("id");
                active = find(selected);
                persist();
                String password = req.optString("password", "");
                if (!password.isEmpty())
                    sessionPasswords.put(selected, password);
                if (!sessionPasswords.containsKey(selected)) {
                    password = vault.load(selected);
                    if (password != null)
                        sessionPasswords.put(selected, password);
                }
                if (!sessionPasswords.containsKey(selected)) {
                    state = "password_required";
                    throw new IllegalArgumentException(
                        "SIP is enabled; enter the session password to reconnect");
                }
                desired = true;
                preferences.edit().putBoolean("enabled", true).commit();
                state = "connecting";
                requestCellular();
                reconcile();
                break;
            }
            case "disconnect":
                desired = false;
                preferences.edit().putBoolean("enabled", false).commit();
                stopEngine();
                releaseCellular();
                state = "disconnected";
                stopForeground(STOP_FOREGROUND_REMOVE);
                stopSelf();
                break;
            case "call": {
                if (!registered || active == null)
                    throw new IllegalArgumentException("Connect a SIP account first");
                if (!"idle".equals(callState))
                    throw new IllegalArgumentException("A SIP call is already active");
                String target = SipPolicy.dial(req.getString("target").trim(),
                    active.getString("host"), active.getInt("port"));
                quality = new JSONObject();
                if (!prepareAudio())
                    throw new IllegalArgumentException(
                        "Microphone permission or audio focus is unavailable");
                SipEngine.command(1, target);
                break;
            }
            case "answer":
                if ("incoming".equals(callState)) {
                    if (!prepareAudio())
                        throw new IllegalArgumentException("Allow microphone access to answer");
                    SipEngine.command(2, "");
                }
                break;
            case "hangup":
                SipEngine.command(3, "");
                break;
            case "mute":
                muted = req.optBoolean("value");
                SipEngine.command(4, muted ? "1" : "0");
                break;
            case "speaker":
                speaker = req.optBoolean("value");
                main.post(() -> route());
                break;
            case "hold":
                SipEngine.command(6, req.optBoolean("value") ? "1" : "0");
                break;
            case "dtmf":
                String digit = req.optString("digit");
                if (!digit.matches("[0-9*#]"))
                    throw new IllegalArgumentException("Invalid keypad digit");
                SipEngine.command(5, digit);
                break;
            default:
                throw new IllegalArgumentException("Unknown SIP action");
        }
        publish();
    }
    private void requestCellular() {
        if (active == null)
            return;
        boolean wanted = !"wifi".equals(active.optString("network", "wifi"));
        if (wanted && !cellularRequested) {
            connectivity.requestNetwork(
                new NetworkRequest.Builder()
                    .addTransportType(NetworkCapabilities.TRANSPORT_CELLULAR)
                    .addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                    .build(),
                cellular);
            cellularRequested = true;
        } else if (!wanted)
            releaseCellular();
    }
    private void releaseCellular() {
        if (cellularRequested) {
            connectivity.unregisterNetworkCallback(cellular);
            cellularRequested = false;
        }
    }
    private Network allowed() {
        if (active == null)
            return null;
        String mode = active.optString("network", "wifi");
        Network mobile = null;
        for (Network n : connectivity.getAllNetworks()) {
            NetworkCapabilities c = connectivity.getNetworkCapabilities(n);
            if (c == null || !c.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                || !c.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED))
                continue;
            if (c.hasTransport(NetworkCapabilities.TRANSPORT_VPN))
                continue;
            if (!"mobile".equals(mode) && c.hasTransport(NetworkCapabilities.TRANSPORT_WIFI))
                return n;
            if (!"wifi".equals(mode) && c.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR))
                mobile = n;
        }
        return mobile;
    }
    private void reconcile() {
        if (!desired)
            return;
        Network n = allowed();
        if (Objects.equals(n, bound) && engine != null && engine.isAlive())
            return;
        stopEngine();
        if (n == null) {
            state = "waiting_for_network";
            networkName = "No allowed network";
            foreground(false);
            publish();
            return;
        }
        if (!connectivity.bindProcessToNetwork(n)) {
            state = "network_failed";
            error = "Could not bind SIP to the selected network";
            publish();
            return;
        }
        bound = n;
        NetworkCapabilities caps = connectivity.getNetworkCapabilities(n);
        networkName = caps != null && caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)
            ? "Wi-Fi"
            : "Mobile data";
        try {
            String user = active.getString("extension"), host = active.getString("host"),
                   password = sessionPasswords.get(selected);
            int port = active.getInt("port");
            LinkProperties links = connectivity.getLinkProperties(n);
            if (links == null || links.getInterfaceName() == null
                || !links.getInterfaceName().matches("[A-Za-z0-9_.-]+"))
                throw new IllegalStateException("No SIP network interface");
            StringBuilder settings =
                new StringBuilder("net_interface " + links.getInterfaceName() + "\n");
            for (java.net.InetAddress dns : links.getDnsServers())
                if (dns instanceof java.net.Inet4Address)
                    settings.append("dns_server ").append(dns.getHostAddress()).append(":53\n");
            String networkConfig = settings.toString();
            state = "registering";
            foreground(false);
            stopping = false;
            long started = generation;
            engine = new Thread(() -> {
                int result;
                try {
                    result = SipEngine.run(this, user, host, port, password, networkConfig);
                } catch (LinkageError e) {
                    result = -1;
                }
                int code = result;
                work.execute(() -> {
                    if (started != generation)
                        return;
                    registered = false;
                    if (desired) {
                        state = "reconnecting";
                        if (code != 0)
                            error = "SIP engine stopped (" + code + "); retrying";
                        int delay = recoveryDelay;
                        recoveryDelay = Math.min(30000, recoveryDelay * 2);
                        main.postDelayed(()
                                             -> work.execute(() -> {
                            if (desired && started == generation)
                                reconcile();
                        }),
                            delay);
                    }
                    publish();
                });
            }, "next-sip-engine");
            engine.start();
        } catch (Exception e) {
            state = "engine_failed";
            error = "SIP account could not start";
        }
        publish();
    }
    private void stopEngine() {
        generation++;
        stopping = true;
        registered = false;
        if (engine != null && engine.isAlive()) {
            stopping = true;
            try {
                SipEngine.command(9, "");
                engine.join(5000);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
            if (engine.isAlive())
                throw new IllegalStateException("SIP is still stopping; retry shortly");
        }
        engine = null;
        bound = null;
        connectivity.bindProcessToNetwork(null);
        callState = "idle";
        releaseAudio();
    }
    private boolean prepareAudio() {
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO)
            != PackageManager.PERMISSION_GRANTED)
            return false;
        AudioAttributes attributes = new AudioAttributes.Builder()
                                         .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
                                         .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                                         .build();
        focus = new AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_EXCLUSIVE)
                    .setAudioAttributes(attributes)
                    .setOnAudioFocusChangeListener(
                        change
                        -> {
                            if (change == AudioManager.AUDIOFOCUS_LOSS
                                || change == AudioManager.AUDIOFOCUS_LOSS_TRANSIENT)
                                SipEngine.command(3, "");
                        },
                        main)
                    .build();
        if (audio.requestAudioFocus(focus) != AudioManager.AUDIOFOCUS_REQUEST_GRANTED)
            return false;
        audio.setMode(AudioManager.MODE_IN_COMMUNICATION);
        main.post(() -> route());
        foreground(true);
        return true;
    }
    private void route() {
        if (Build.VERSION.SDK_INT >= 31) {
            int wanted = speaker ? AudioDeviceInfo.TYPE_BUILTIN_SPEAKER
                                 : AudioDeviceInfo.TYPE_BUILTIN_EARPIECE;
            AudioDeviceInfo choice = null;
            for (AudioDeviceInfo d : audio.getAvailableCommunicationDevices()) {
                if (!speaker
                    && (d.getType() == AudioDeviceInfo.TYPE_BLUETOOTH_SCO
                        || d.getType() == AudioDeviceInfo.TYPE_BLE_HEADSET
                        || d.getType() == AudioDeviceInfo.TYPE_WIRED_HEADSET)) {
                    choice = d;
                    break;
                }
                if (d.getType() == wanted)
                    choice = d;
            }
            if (choice != null)
                audio.setCommunicationDevice(choice);
        } else
            audio.setSpeakerphoneOn(speaker);
    }
    private void releaseAudio() {
        onAudioSession(0);
        getSystemService(NotificationManager.class).cancel(INCOMING);
        main.post(() -> {
            if (focus != null) {
                audio.abandonAudioFocusRequest(focus);
                focus = null;
                if (Build.VERSION.SDK_INT >= 31)
                    audio.clearCommunicationDevice();
                else
                    audio.setSpeakerphoneOn(false);
                audio.setMode(AudioManager.MODE_NORMAL);
            }
        });
        muted = false;
        speaker = false;
    }
    public void onNativeEvent(String value, String remote, int code) {
        if ("ready".equals(value) && stopping) {
            SipEngine.command(9, "");
            return;
        }
        if (stopping)
            return;
        long emitted = generation;
        work.execute(() -> {
            if (emitted != generation)
                return;
            switch (value) {
                case "registering":
                    state = value;
                    break;
                case "registered":
                    registered = true;
                    error = "";
                    recoveryDelay = 1000;
                    state = value;
                    foreground(focus != null);
                    break;
                case "registration_failed":
                    registered = false;
                    state = value;
                    error = "SIP registration rejected (" + code
                        + " ); check account settings or server connection limits";
                    foreground(focus != null);
                    break;
                case "incoming":
                case "calling":
                case "ringing":
                case "progress":
                case "connected":
                    callState = value;
                    peer = remote;
                    if ("incoming".equals(value)) {
                        Notification n = new Notification.Builder(this, "sip_calls")
                                             .setSmallIcon(R.drawable.ic_stat_meshchatnext)
                                             .setContentTitle("Incoming SIP call")
                                             .setContentText(remote)
                                             .setContentIntent(open())
                                             .setCategory(Notification.CATEGORY_CALL)
                                             .setOngoing(true)
                                             .build();
                        n.flags |= Notification.FLAG_INSISTENT;
                        getSystemService(NotificationManager.class).notify(INCOMING, n);
                    } else if ("connected".equals(value))
                        getSystemService(NotificationManager.class).cancel(INCOMING);
                    break;
                case "ended":
                                            callState = "idle";
                    peer = "";
                    releaseAudio();
                    foreground(false);
                    break;
                case "audio_error":
                    error = "SIP audio device failed; end the call and retry";
                    break;
                case "command_failed":
                    error = "SIP call action failed (" + code + ")";
                    if ("idle".equals(callState))
                        releaseAudio();
                    break;
                case "engine_failed":
                    state = value;
                    error = "SIP engine failed (" + code + ")";
                    break;
                default:
                    break;
            }
            publish();
        });
    }
    private void publish() {
        try {
            JSONArray safe = new JSONArray();
            for (int i = 0; i < accounts.length(); i++) {
                JSONObject a = new JSONObject(accounts.getJSONObject(i).toString());
                a.put("has_password",
                    vault.has(a.getString("id"))
                        || sessionPasswords.containsKey(a.getString("id")));
                safe.put(a);
            }
            String json =
                new JSONObject()
                    .put("available", true)
                    .put("i2p_available", false)
                    .put("last_request", lastRequest)
                    .put("request_error", requestError)
                    .put("state", state)
                    .put("registered", registered)
                    .put("enabled", preferences.getBoolean("enabled", false))
                    .put("call_state", callState)
                    .put("peer", peer)
                    .put("error", error)
                    .put("network", networkName)
                    .put("selected", selected)
                    .put("accounts", safe)
                    .put("muted", muted)
                    .put("speaker", speaker)
                    .put("quality", quality)
                    .toString();
            main.post(() -> {
                Iterator<Messenger> it = listeners.iterator();
                while (it.hasNext()) {
                    Messenger target = it.next();
                    Message m = Message.obtain(null, 2);
                    Bundle b = new Bundle();
                    b.putString("json", json);
                    m.setData(b);
                    try {
                        target.send(m);
                    } catch (RemoteException e) {
                        it.remove();
                    }
                }
            });
        } catch (JSONException ignored) {
        }
    }
    @Override
    public void onDestroy() {
        desired = false;
        releaseCellular();
        connectivity.unregisterNetworkCallback(callback);
        work.execute(() -> {
            stopEngine();
            work.shutdown();
        });
        super.onDestroy();
    }
}
