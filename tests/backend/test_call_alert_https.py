# SPDX-License-Identifier: 0BSD
"""Exercise the actual sender over validated, loopback-only TLS."""

import json
import ssl
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import RNS
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from meshchatnext.src.backend import call_alerts
from meshchatnext.src.backend.call_wake import build_hint, signed_bytes


@pytest.fixture
def https_peer(tmp_path, monkeypatch):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Private call test")])
    import ipaddress

    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(minutes=1))
        .not_valid_after(datetime.now(UTC) + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
            ),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    certificate = tmp_path / "local-test-ca.pem"
    certificate.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    private = tmp_path / "local-test-server.pem"
    private.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    private.chmod(0o600)
    received = []
    redirect = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            raw = self.rfile.read(int(self.headers["Content-Length"]))
            received.append(
                (self.path, self.headers.get("Content-Type"), json.loads(raw))
            )
            self.send_response(302 if redirect.is_set() else 204)
            if redirect.is_set():
                self.send_header(
                    "Location",
                    f"https://127.0.0.1:{self.server.server_port}/do-not-follow",
                )
            self.end_headers()

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certificate, private)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
    )
    thread.start()
    monkeypatch.setenv("SSL_CERT_FILE", str(certificate))
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    identity = RNS.Identity()
    route = call_alerts.Route(
        f"https://127.0.0.1:{server.server_port}",
        "private-calls",
        RNS.Identity().get_public_key().hex(),
    )
    try:
        yield route, identity, received, redirect
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def test_https_post_carries_exact_signed_body_and_operation(https_peer):
    route, identity, received, _ = https_peer
    for operation in ("call-alert", "call-cancel"):
        packet = build_hint(
            identity, route.voice, route.audience, cancel=operation == "call-cancel"
        )
        assert call_alerts.post(route, operation, json.dumps(packet).encode()) == 204
        path, content_type, actual = received[-1]
        assert path == "/v1/" + operation and content_type == "application/json"
        assert actual == packet
        assert identity.validate(
            bytes.fromhex(actual["signature"]),
            signed_bytes(actual, route.audience, cancel=operation == "call-cancel"),
        )
    assert len(received) == 2


def test_https_post_never_follows_provider_redirect(https_peer):
    route, identity, received, redirect = https_peer
    redirect.set()
    packet = build_hint(identity, route.voice, route.audience)
    assert call_alerts.post(route, "call-alert", json.dumps(packet).encode()) == 302
    assert len(received) == 1 and received[0][0] == "/v1/call-alert"


def test_https_post_rejects_untrusted_certificate(https_peer, monkeypatch):
    route, identity, received, _ = https_peer
    monkeypatch.delenv("SSL_CERT_FILE")
    packet = build_hint(identity, route.voice, route.audience)
    assert call_alerts.post(route, "call-alert", json.dumps(packet).encode()) == 503
    assert received == []
