/* SPDX-License-Identifier: 0BSD */
#include <jni.h>
#include <pthread.h>
#include <re.h>
#include <stdlib.h>
#include <string.h>
#define DEBUG_MODULE "next_sip"
#define DEBUG_LEVEL 0
#include <baresip.h>
#include <re_dbg.h>
static JavaVM *vm;
static jobject listener;
static jmethodID event_method;
static struct mqueue *queue;
static struct ua *agent;
static struct call *current;
static struct tmr digit_timer;
static struct tmr shutdown_timer;
/* Keep the existing UDP mapping alive without creating another registration. */
static struct tmr keepalive_timer;
static bool keepalive_enabled, keepalive_pending;
static char keepalive_uri[384];
static void keepalive_tick(void *arg);
static void keepalive_response(int err, const struct sip_msg *msg, void *arg);

static void finish_shutdown(void *arg) { (void)arg; re_cancel(); }
static void release_digit(void *arg){(void)arg;if(current)call_send_digit(current,KEYCODE_REL);}
static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
static void event(const char *state, const char *peer, int code) {
    JNIEnv *env = NULL;
    bool attached = false;
    if ((*vm)->GetEnv(vm, (void **)&env, JNI_VERSION_1_6) != JNI_OK) {
        if ((*vm)->AttachCurrentThread(vm, &env, NULL) != JNI_OK) return;
        attached = true;
    }
    jstring s = (*env)->NewStringUTF(env, state);
    /* Peers are ASCII SIP URIs, never account parameters or event text. */
    jstring p = (*env)->NewStringUTF(env, peer ? peer : "");
    (*env)->CallVoidMethod(env, listener, event_method, s, p, code);
    if ((*env)->ExceptionCheck(env)) (*env)->ExceptionClear(env);
    (*env)->DeleteLocalRef(env, s);
    (*env)->DeleteLocalRef(env, p);
    if (attached) (*vm)->DetachCurrentThread(vm);
}

static void keepalive_response(int err, const struct sip_msg *msg, void *arg) {
    (void)arg;
    keepalive_pending = false;
    if (!keepalive_enabled || !agent) return;
    event("keepalive", NULL, err ? -err : (msg ? msg->scode : 0));
    tmr_start(&keepalive_timer, 20000, keepalive_tick, NULL);
}
static void keepalive_tick(void *arg) {
    (void)arg;
    if (!keepalive_enabled || !agent || keepalive_pending) return;
    keepalive_pending = true;
    int err = ua_options_send(agent, keepalive_uri, keepalive_response, NULL);
    if (err) keepalive_response(err, NULL, NULL);
}
/* AAudio allocates a recording session for Android's hardware audio effects. */
void next_sip_audio_session(int session) {
    JNIEnv *env = NULL;
    bool attached = false;
    if ((*vm)->GetEnv(vm, (void **)&env, JNI_VERSION_1_6) != JNI_OK) {
        if ((*vm)->AttachCurrentThread(vm, &env, NULL) != JNI_OK) return;
        attached = true;
    }
    jmethodID method =
        (*env)->GetMethodID(env, (*env)->GetObjectClass(env, listener), "onAudioSession", "(I)V");
    if (method) (*env)->CallVoidMethod(env, listener, method, session);
    if ((*env)->ExceptionCheck(env)) (*env)->ExceptionClear(env);
    if (attached) (*vm)->DetachCurrentThread(vm);
}
static void stats(struct call *c) {
    if (!c) return;
    const struct rtcp_stats *s = stream_rtcp_stats(audio_strm(call_audio(c)));
    if (!s) return;
    JNIEnv *env = NULL;
    if ((*vm)->GetEnv(vm, (void **)&env, JNI_VERSION_1_6) != JNI_OK) return;
    char json[512];
    re_snprintf(json, sizeof(json),
                "{\"sent\":%u,\"received\":%u,\"lost_tx\":%d,\"lost_rx\":%d,\"jitter_ms\":%u,\"rtt_"
                "ms\":%u}",
                s->tx.sent, s->rx.sent, s->tx.lost, s->rx.lost, s->rx.jit / 1000, s->rtt / 1000);
    jmethodID method = (*env)->GetMethodID(env, (*env)->GetObjectClass(env, listener),
                                           "onCallStats", "(Ljava/lang/String;)V");
    jstring value = (*env)->NewStringUTF(env, json);
    if (method) (*env)->CallVoidMethod(env, listener, method, value);
    if ((*env)->ExceptionCheck(env)) (*env)->ExceptionClear(env);
    (*env)->DeleteLocalRef(env, value);
}
static void events(enum bevent_ev ev, struct bevent *e, void *arg) {
    (void)arg;
    struct call *c = bevent_get_call(e);
    switch (ev) {
        case BEVENT_REGISTERING:
            event("registering", NULL, 0);
            break;
        case BEVENT_REGISTER_OK:
            keepalive_enabled = true;
            if (!keepalive_pending) tmr_start(&keepalive_timer, 20000, keepalive_tick, NULL);
            event("registered", NULL, 0);
            break;
        case BEVENT_REGISTER_FAIL: {
            keepalive_enabled = false;
            tmr_cancel(&keepalive_timer);
            const char *text = bevent_get_text(e);
            int code = 0;
            if (text && text[0] >= '0' && text[0] <= '9')
                code = atoi(text);
            else if (text) {
                for (int n = 1; n < 200; n++)
                    if (!strcmp(text, strerror(n))) {
                        code = -n;
                        break;
                    }
            }
            event("registration_failed", NULL, code);
            break;
        }
        case BEVENT_CALL_INCOMING:
            if (current && current != c) {
                call_hangup(c, 486, "Busy");
                break;
            }
            current = c;
            event("incoming", call_peeruri(c), 0);
            break;
        case BEVENT_CALL_OUTGOING:
            current = c;
            event("calling", call_peeruri(c), 0);
            break;
        case BEVENT_CALL_RINGING:
            event("ringing", call_peeruri(c), 0);
            break;
        case BEVENT_CALL_PROGRESS:
            event("progress", call_peeruri(c), 0);
            break;
        case BEVENT_CALL_ESTABLISHED:
            event("connected", call_peeruri(c), 0);
            break;
        case BEVENT_CALL_RTCP:
            stats(c);
            break;
        case BEVENT_CALL_CLOSED:
            tmr_cancel(&digit_timer);
            stats(c);
            if (current == c) {
                current = NULL;
                event("ended", call_peeruri(c), 0);
            }
            break;
        case BEVENT_AUDIO_ERROR:
            event("audio_error", NULL, 0);
            break;
        default:
            break;
    }
}
static void commands(int id, void *data, void *arg) {
    (void)arg;
    int err = 0;
    char *text = data;
    switch (id) {
        case 1:
            if (!current && agent)
                err = ua_connect(agent, &current, NULL, text, VIDMODE_OFF);
            else
                err = EBUSY;
            break;
        case 2:
            if (current) err = ua_answer(agent, current, VIDMODE_OFF);
            break;
        case 3:
            if (current) ua_hangup(agent, current, 0, NULL);
            break;
        case 4:
            if (current) audio_mute(call_audio(current), text && text[0] == '1');
            break;
        case 5:
            if (current && text && text[0]) {err = call_send_digit(current, text[0]);tmr_start(&digit_timer,150,release_digit,NULL);}
            break;
        case 6:
            if (current) err = call_hold(current, text && text[0] == '1');
            break;
        case 9:
            keepalive_enabled = false;
            tmr_cancel(&keepalive_timer);
            /* Allow the authenticated expires=0 transaction to finish before
               stopping the event loop. Never wait indefinitely for a dead network. */
            if (agent) {
                if (current) ua_hangup(agent, current, 0, NULL);
                ua_unregister(agent);
            }
            tmr_start(&shutdown_timer, 1500, finish_shutdown, NULL);
            break;
    }
    if (err) event("command_failed", NULL, err);
    mem_deref(data);
}
JNIEXPORT void JNICALL Java_com_meshchatnext_sip_SipEngine_command(JNIEnv *env, jclass cls, jint id,
                                                                   jstring value) {
    (void)cls;
    char *copy = NULL;
    if (value) {
        const char *s = (*env)->GetStringUTFChars(env, value, NULL);
        str_dup(&copy, s);
        (*env)->ReleaseStringUTFChars(env, value, s);
    }
    pthread_mutex_lock(&lock);
    if (!queue || mqueue_push(queue, id, copy)) mem_deref(copy);
    pthread_mutex_unlock(&lock);
}
JNIEXPORT jint JNICALL Java_com_meshchatnext_sip_SipEngine_run(JNIEnv *env, jclass cls,
                                                               jobject target, jstring juser,
                                                               jstring jhost, jint port,
                                                               jstring jpass, jstring jnetwork) {
    (void)cls;
    int err = 0;
    char aor[768];
    const char *user = (*env)->GetStringUTFChars(env, juser, NULL);
    const char *host = (*env)->GetStringUTFChars(env, jhost, NULL);
    const char *network = (*env)->GetStringUTFChars(env, jnetwork, NULL);
    const char *pass = (*env)->GetStringUTFChars(env, jpass, NULL);
    listener = (*env)->NewGlobalRef(env, target);
    event_method = (*env)->GetMethodID(env, (*env)->GetObjectClass(env, target), "onNativeEvent",
                                       "(Ljava/lang/String;Ljava/lang/String;I)V");
    log_enable_stdout(false);
    log_enable_debug(false);
    log_enable_info(false);
    dbg_init(DBG_EMERG, 0);
    err = libre_init();
    if (err) goto finish;
    re_thread_async_init(2);
    const char *config =
        "audio_player aaudio,default\naudio_source aaudio,default\naudio_alert "
        "aaudio,default\naudio_buffer 20-160\naudio_jitter_buffer_type "
        "adaptive\naudio_jitter_buffer_ms 40-200\nrtp_stats no\ncall_max_calls 1\ncall_accept "
        "yes\nnet_af ipv4\nsip_cuser_random no\nsip_listen 0.0.0.0:5072\n";
    char *full = NULL;
    re_sdprintf(&full, "%s%s", config, network);
    err = conf_configure_buf((const uint8_t *)full, strlen(full));
    mem_deref(full);
    if (err) goto close;
    err = baresip_init(conf_config());
    if (err) goto close;
    err = ua_init("Meshchat-neXt SIP", true, false, false);
    if (err) goto close;
    const char *modules[] = {"aaudio", "g711", "opus", NULL};
    for (int i = 0; modules[i]; i++) {
        err = module_preload(modules[i]);
        if (err) goto close;
    }
    err = bevent_register(events, NULL);
    if (err) goto close;
    keepalive_enabled = keepalive_pending = false;
    re_snprintf(keepalive_uri, sizeof(keepalive_uri), "sip:%s:%d;transport=udp", host, port);
    re_snprintf(aor, sizeof(aor),
                "<sip:%s@%s:%d;transport=udp>;regint=0;audio_codecs=opus/48000/2,PCMU/8000/1,PCMA/"
                "8000/1;ptime=20;rtpkeep=zero",
                user, host, port);
    err = ua_alloc(&agent, aor);
    if (err) goto close;
    /* call_accept creates CALL_STATE_INCOMING only (upstream call.c).
       No audio is answered until explicit command 2 invokes ua_answer. */
    account_set_answermode(ua_account(agent), ANSWERMODE_MANUAL);
    account_set_sip_autoanswer(ua_account(agent), false);
    err = account_set_auth_user(ua_account(agent), user);
    if (err) goto close;
    err = account_set_auth_pass(ua_account(agent), pass);
    if (err) goto close;
    account_set_regint(ua_account(agent), 3600);
    (*env)->ReleaseStringUTFChars(env, jpass, pass);
    pass = NULL;
    pthread_mutex_lock(&lock);
    err = mqueue_alloc(&queue, commands, NULL);
    pthread_mutex_unlock(&lock);
    if (err) goto close;
    err = ua_register(agent);
    if (err) goto close;
    event("ready", NULL, 0);
    err = re_main(NULL);
close:
    pthread_mutex_lock(&lock);
    queue = mem_deref(queue);
    pthread_mutex_unlock(&lock);
    keepalive_enabled = false;
    tmr_cancel(&keepalive_timer);
    tmr_cancel(&digit_timer);
    tmr_cancel(&shutdown_timer);
    current = NULL;
    agent = NULL;
    bevent_unregister(events);
    ua_stop_all(true);
    ua_close();
    baresip_close();
    conf_close();
    mod_close();
    re_thread_async_close();
    libre_close();
finish:
    if (pass) (*env)->ReleaseStringUTFChars(env, jpass, pass);
    (*env)->ReleaseStringUTFChars(env, jnetwork, network);
    (*env)->ReleaseStringUTFChars(env, juser, user);
    (*env)->ReleaseStringUTFChars(env, jhost, host);
    if (err) event("engine_failed", NULL, err);
    (*env)->DeleteGlobalRef(env, listener);
    listener = NULL;
    return err;
}
JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM *jvm, void *reserved) {
    (void)reserved;
    vm = jvm;
    return JNI_VERSION_1_6;
}
