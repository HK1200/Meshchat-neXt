/* SPDX-License-Identifier: 0BSD */
/* Private stdin/stdout JSON control. Never accepts credentials in argv/files. */
#include <re.h>
#include <baresip.h>
#define DEBUG_MODULE "next_sip_linux"
#define DEBUG_LEVEL 0
#include <re_dbg.h>
#include <unistd.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <ctype.h>
#include <errno.h>
#include <stdlib.h>
#include <sys/socket.h>
#include <net/if.h>
static const char *bound_interface;
int __real_socket(int domain, int type, int protocol);
int __wrap_socket(int domain, int type, int protocol) {
    int fd = __real_socket(domain, type, protocol);
    if (fd >= 0 && bound_interface && (domain == AF_INET || domain == AF_INET6)) {
        if (setsockopt(fd, SOL_SOCKET, SO_BINDTODEVICE, bound_interface, strlen(bound_interface)+1)) {
            int saved = errno; close(fd); errno = saved; return -1;
        }
    }
    return fd;
}
static struct ua *agent;
static struct call *current;
static struct re_fhs *input;
static struct tmr shutdown_timer;
static struct tmr digit_timer;
static void release_digit(void *arg) {(void)arg; if (current) call_send_digit(current, KEYCODE_REL);}
static char buffer[4096];
static size_t used;
static bool stopping;
static int output(const char *p, size_t n, void *arg) {
    (void)arg;
    return fwrite(p, 1, n, stdout) == n ? 0 : EIO;
}
static void emit(const char *state, const char *peer, int code, const char *id) {
    struct odict *od = NULL;
    struct re_printf pf = {output, NULL};
    if (odict_alloc(&od, 8)) return;
    odict_entry_add(od, "state", ODICT_STRING, state);
    odict_entry_add(od, "peer", ODICT_STRING, peer ? peer : "");
    odict_entry_add(od, "code", ODICT_INT, (int64_t)code);
    if (id) odict_entry_add(od, "id", ODICT_STRING, id);
    json_encode_odict(&pf, od);
    fputc('\n', stdout); fflush(stdout);
    mem_deref(od);
}
static void emit_stats(const char *id) {
    const struct rtcp_stats *stats = stream_rtcp_stats(audio_strm(call_audio(current)));
    struct odict *od = NULL;
    struct re_printf pf = {output, NULL};
    if (!stats || odict_alloc(&od, 8)) return;
    odict_entry_add(od, "state", ODICT_STRING, "stats");
    odict_entry_add(od, "id", ODICT_STRING, id);
    odict_entry_add(od, "sent", ODICT_INT, (int64_t)stats->tx.sent);
    odict_entry_add(od, "received", ODICT_INT, (int64_t)stats->rx.sent);
    odict_entry_add(od, "lost_rx", ODICT_INT, (int64_t)stats->rx.lost);
    odict_entry_add(od, "jitter_ms", ODICT_INT, (int64_t)(stats->rx.jit / 1000));
    odict_entry_add(od, "rtt_ms", ODICT_INT, (int64_t)(stats->rtt / 1000));
    json_encode_odict(&pf, od); fputc('\n', stdout); fflush(stdout); mem_deref(od);
}
static void finish(void *arg) { (void)arg; re_cancel(); }
static void stop(void) {
    if (stopping) return;
    stopping = true;
    input = fd_close(input);
    if (agent) {
        if (current) ua_hangup(agent, current, 0, NULL);
        ua_unregister(agent);
    }
    tmr_start(&shutdown_timer, 1500, finish, NULL);
}
static void events(enum bevent_ev ev, struct bevent *e, void *arg) {
    (void)arg;
    struct call *c = bevent_get_call(e);
    switch (ev) {
    case BEVENT_REGISTERING: emit("registering", NULL, 0, NULL); break;
    case BEVENT_REGISTER_OK: emit("registered", NULL, 0, NULL); break;
    case BEVENT_REGISTER_FAIL: emit("registration_failed", NULL, bevent_get_text(e) ? atoi(bevent_get_text(e)) : 0, NULL); break;
    case BEVENT_CALL_INCOMING:
        if (current && current != c) { call_hangup(c, 486, "Busy"); break; }
        current = c; emit("incoming", call_peeruri(c), 0, NULL); break;
    case BEVENT_CALL_OUTGOING: current = c; emit("calling", call_peeruri(c), 0, NULL); break;
    case BEVENT_CALL_RINGING: emit("ringing", call_peeruri(c), 0, NULL); break;
    case BEVENT_CALL_ESTABLISHED: emit("connected", call_peeruri(c), 0, NULL); break;
    case BEVENT_CALL_CLOSED:
        tmr_cancel(&digit_timer);
        if (current == c) {current = NULL; emit("ended", call_peeruri(c), 0, NULL);} break;
    case BEVENT_AUDIO_ERROR: emit("audio_error", NULL, 0, NULL); break;
    default: break;
    }
}
static bool safe_name(const char *s, size_t max, bool host) {
    if (!s || !*s || strlen(s) > max) return false;
    for (; *s; ++s) if (!(isalnum((unsigned char)*s) || *s == '.' || *s == '-' || (!host && *s == '_'))) return false;
    return true;
}
static void command(char *line, size_t len) {
    struct odict *od = NULL;
    int err = json_decode_odict(&od, 16, line, len, 4);
    if (err) { emit("command_failed", NULL, EINVAL, NULL); return; }
    const char *op = odict_string(od, "op"), *id = odict_string(od, "id");
    bool value = false;
    odict_get_boolean(od, &value, "value");
    if (!op || !id || strlen(id) > 64) {err = EINVAL; goto done;}
    if (!strcmp(op, "start")) {
        const char *user = odict_string(od, "user"), *host = odict_string(od, "host");
        const char *password = odict_string(od, "password");
        uint64_t port = 0;
        odict_get_number(od, &port, "port");
        char aor[768];
        if (agent) {err = EALREADY; goto done;}
        if (!safe_name(user, 64, false) || !safe_name(host, 253, true) || !port || port > 65535 || !password || strlen(password) > 256) {err = EINVAL; goto done;}
        re_snprintf(aor, sizeof(aor), "<sip:%s@%s:%u;transport=udp>;regint=0;audio_codecs=opus/48000/2,PCMU/8000/1,PCMA/8000/1;ptime=20;rtpkeep=zero", user, host, (unsigned)port);
        err = ua_alloc(&agent, aor);
        if (err) goto done;
        account_set_answermode(ua_account(agent), ANSWERMODE_MANUAL);
        account_set_sip_autoanswer(ua_account(agent), false);
        err = account_set_auth_user(ua_account(agent), user);
        if (!err) err = account_set_auth_pass(ua_account(agent), password);
        if (!err) {account_set_regint(ua_account(agent), 3600); err = ua_register(agent);}
        if (err) agent = mem_deref(agent);
    } else if (!strcmp(op, "dial")) {
        const char *peer = odict_string(od, "peer");
        if (!agent || current) err = EBUSY;
        else if (!peer || strlen(peer) > 320 || strncmp(peer,"sip:",4) || strpbrk(peer,"\r\n\"<> ")) err = EINVAL;
        else err = ua_connect(agent, &current, NULL, peer, VIDMODE_OFF);
    } else if (!strcmp(op, "answer")) {
        err = current ? ua_answer(agent, current, VIDMODE_OFF) : ENOENT;
    } else if (!strcmp(op, "hangup")) {
        if (current) ua_hangup(agent, current, 0, NULL); else err = ENOENT;
    } else if (!strcmp(op, "mute")) {
        if (current) audio_mute(call_audio(current), value); else err = ENOENT;
    } else if (!strcmp(op, "hold")) {
        err = current ? call_hold(current, value) : ENOENT;
    } else if (!strcmp(op, "stats")) {
        if (current) {emit_stats(id); goto release;} else err = ENOENT;
    } else if (!strcmp(op, "digit")) {
        const char *digit = odict_string(od, "digit");
        if (!current) err = ENOENT;
        else if (!digit || strlen(digit) != 1 || !strchr("0123456789*#ABCD", digit[0])) err = EINVAL;
        else {err = call_send_digit(current, digit[0]); if (!err) tmr_start(&digit_timer, 150, release_digit, NULL);}
    } else if (!strcmp(op, "stop")) stop();
    else if (strcmp(op, "ping")) err = EINVAL;
 done:
    emit(err ? "command_failed" : "ok", NULL, err, id);
 release:
    mem_deref(od);
}
static void read_input(int flags, void *arg) {
    (void)arg;
    if (!(flags & FD_READ)) {if (flags & FD_EXCEPT) stop(); return;}
    char chunk[512]; ssize_t n = read(STDIN_FILENO, chunk, sizeof(chunk));
    if (n <= 0) {stop(); return;}
    for (ssize_t i=0; i<n; ++i) {
        if (chunk[i] == '\n') {
            buffer[used] = 0; command(buffer, used);
            memset(buffer, 0, sizeof(buffer)); used=0;
            if (stopping) return;
        } else if (!chunk[i] || used >= sizeof(buffer)-1) {
            emit("protocol_error", NULL, EOVERFLOW, NULL); stop(); return;
        } else buffer[used++] = chunk[i];
    }
    memset(chunk, 0, sizeof(chunk));
}
int main(int argc, char **argv) {
    bool test = false;
    for (int i=1; i<argc; ++i) {
        if (!strcmp(argv[i], "--test-audio")) test = true;
        else if (!strcmp(argv[i], "--interface") && i+1<argc) bound_interface = argv[++i];
        else return 2;
    }
    if (test && !bound_interface) bound_interface = "lo";
    if (bound_interface) {
        if (!*bound_interface || strlen(bound_interface) >= IFNAMSIZ || !if_nametoindex(bound_interface)) return 2;
        for (const char *p=bound_interface; *p; ++p)
            if (!(isalnum((unsigned char)*p) || strchr("_.:-",*p))) return 2;
    }
    signal(SIGPIPE, SIG_IGN);
    log_enable_stdout(false); log_enable_debug(false); log_enable_info(false); dbg_init(DBG_EMERG, 0);
    int err = libre_init();
    if (err) return 1;
    re_thread_async_init(2);
    /* Delegate hostname lookup to the OS resolver: the systemd DNS stub is
       loopback-only and cannot be reached by a Wi-Fi-bound UDP DNS socket.
       SIP/RTP sockets remain bound to the explicitly selected interface. */
    const char *config = test ?
        "audio_player aufile,/dev/null\naudio_source ausine,440\naudio_alert aufile,/dev/null\nsip_listen 127.0.0.1:0\nnet_interface 127.0.0.1\nnet_af ipv4\ncall_accept yes\ncall_max_calls 1\n" :
        "dns_getaddrinfo yes\naudio_player pulse,default\naudio_source pulse,default\naudio_alert pulse,default\nsip_listen 0.0.0.0:0\nnet_af ipv4\ncall_accept yes\ncall_max_calls 1\n";
    char selected_config[1024];
    if (bound_interface && !test) {
        re_snprintf(selected_config, sizeof(selected_config), "%snet_interface %s\n", config, bound_interface);
        config = selected_config;
    }
    err = conf_configure_buf((const uint8_t *)config, strlen(config));
    if (!err) err = baresip_init(conf_config());
    if (!err) err = ua_init("Meshchat-neXt Linux SIP", true, false, false);
    const char *modules[] = {"g711", "opus", test ? "ausine" : "pulse", test ? "aufile" : NULL, NULL};
    for (int i=0; !err && modules[i]; ++i) err = module_preload(modules[i]);
    if (!err) err = bevent_register(events, NULL);
    if (!err) err = fd_listen(&input, STDIN_FILENO, FD_READ | FD_EXCEPT, read_input, NULL);
    if (!err) {emit("ready", NULL, 0, NULL); err = re_main(NULL);}
    input=fd_close(input); tmr_cancel(&shutdown_timer); tmr_cancel(&digit_timer);
    bevent_unregister(events); ua_stop_all(true); ua_close(); baresip_close(); conf_close(); mod_close();
    re_thread_async_close(); libre_close(); memset(buffer,0,sizeof(buffer));
    return err ? 1 : 0;
}
