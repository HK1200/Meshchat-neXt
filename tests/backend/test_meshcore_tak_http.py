# SPDX-License-Identifier: 0BSD
import asyncio
import base64
import datetime
import hashlib
import io
import ssl
import zipfile

import pytest
from aiohttp import web
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from meshchatnext.src.backend.meshcore_cot import CotSession
from meshchatnext.src.backend.meshcore_tak_http import (
    TakWebClient,
    validate_package,
)


def package():
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr(
            "MANIFEST/manifest.xml",
            '<MissionPackageManifest version="2"><Configuration/><Contents/></MissionPackageManifest>',
        )
    return data.getvalue()


@pytest.mark.asyncio
async def test_https_enrollment_mutual_tls_and_verified_package_transfer(tmp_path):
    now = datetime.datetime.now(datetime.UTC)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    ca = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=1))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), True)
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), False)
        .sign(key, hashes.SHA256())
    )
    cert_file, key_file = tmp_path / "server.pem", tmp_path / "server.key"
    cert_file.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_file, key_file)
    store = {}
    visibility = []

    async def config(request):
        assert (
            request.headers.get("Authorization") == "Basic dGVzdC11c2VyOnRlc3QtcGFzcw=="
        )
        return web.Response(
            text='<certificateConfig><nameEntries><entry name="O" value="neXt test"/></nameEntries></certificateConfig>'
        )

    async def sign(request):
        csr = x509.load_pem_x509_csr(await request.read())
        assert csr.is_signature_valid
        assert (
            csr.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
            == "test-user"
        )
        certificate = (
            x509.CertificateBuilder()
            .subject_name(csr.subject)
            .issuer_name(ca.subject)
            .public_key(csr.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=1))
            .not_valid_after(now + datetime.timedelta(hours=1))
            .sign(key, hashes.SHA256())
        )
        return web.Response(
            body=certificate.public_bytes(serialization.Encoding.PEM)
            + ca.public_bytes(serialization.Encoding.PEM)
        )

    async def upload(request):
        multipart = await request.multipart()
        field = await multipart.next()
        assert field.name == "assetfile"
        raw = await field.read()
        assert hashlib.sha256(raw).hexdigest() == request.query["hash"]
        store[request.query["hash"]] = raw
        return web.Response(text="https://localhost/Marti/api/sync/content")

    async def set_visibility(request):
        visibility.append(await request.text())
        return web.Response(text="ok")

    async def search(request):
        return web.json_response(
            {"results": [{"hash": h, "name": "Synthetic package"} for h in store]}
        )

    async def download(request):
        return web.Response(body=store.get(request.query["hash"], b"corrupt"))

    app = web.Application()
    app.router.add_get("/Marti/api/tls/config", config)
    app.router.add_post("/Marti/api/tls/signClient", sign)
    app.router.add_post("/Marti/sync/missionupload", upload)
    app.router.add_put("/Marti/api/sync/metadata/{digest}/tool", set_visibility)
    app.router.add_get("/Marti/api/sync/search", search)
    app.router.add_get("/Marti/api/sync/content", download)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0, ssl_context=context)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    cert_text = cert_file.read_text()
    session = CotSession(tmp_path)
    stream = None
    try:
        result = await session.enroll(
            "localhost", port, "test-user", "test-pass", cert_text
        )
        assert result["enrolled"] and "private_key" not in result
        mutual = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        mutual.load_cert_chain(cert_file, key_file)
        mutual.load_verify_locations(cafile=cert_file)
        mutual.verify_mode = ssl.CERT_REQUIRED
        got_client = asyncio.Event()

        async def handler(reader, writer):
            try:
                assert writer.get_extra_info("peercert")
                got_client.set()
                await reader.read()
            finally:
                writer.close()

        stream = await asyncio.start_server(handler, "127.0.0.1", 0, ssl=mutual)
        await session.connect(
            "localhost",
            stream.sockets[0].getsockname()[1],
            https_port=port,
            ca=cert_text,
        )
        await asyncio.wait_for(got_client.wait(), 2)
        assert not list(tmp_path.glob("tak-tls-*"))
        raw = package()
        digest = hashlib.sha256(raw).hexdigest()
        uploaded = await session.package_upload(
            base64.b64encode(raw).decode(), "synthetic.zip", private=True
        )
        assert uploaded["hash"] == digest and visibility == ["private"]
        assert (await session.package_search())[0]["hash"] == digest
        downloaded = await session.package_download(digest)
        assert base64.b64decode(downloaded["zip_base64"]) == raw
        with pytest.raises(ValueError, match="hash"):
            await session.package_download("0" * 64)
        await session.close()
        assert session.web is None and session.enrollment is None
    finally:
        await session.close()
        await runner.cleanup()
        if stream:
            stream.close()
            await stream.wait_closed()


def test_reject_bad_packages_and_credentials():
    with pytest.raises(ValueError):
        validate_package(b"not a zip")
    context = ssl.create_default_context()
    with pytest.raises(ValueError):
        TakWebClient("https://other.example", 443, context)
    with pytest.raises(ValueError):
        TakWebClient("localhost", True, context)
