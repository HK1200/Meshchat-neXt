# SPDX-License-Identifier: 0BSD
"""Explicit, bounded HTTPS TAK enrollment and mission-package transfer."""

from __future__ import annotations

import asyncio
import base64
import datetime
import hashlib
import io
import json
import re
import ssl
import struct
import uuid
import zipfile

import aiohttp
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from yarl import URL

from meshchatnext.src.backend.meshcore_tak_protocol import safe_xml

PACKAGE_LIMIT = 10 * 1024 * 1024
HASH = re.compile(r"^[0-9a-f]{64}$")


def validate_host_port(host, port):
    if (
        not isinstance(host, str)
        or not host
        or len(host) > 253
        or any(c in host for c in "/\\@\r\n\t ")
    ):
        raise ValueError("Invalid TAK server hostname")
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("Invalid HTTPS port")


def validate_package(data):
    try:
        return _validate_package(data)
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError, EOFError) as error:
        raise ValueError("Invalid TAK package archive") from error


def _validate_package(data):
    if not data or len(data) > PACKAGE_LIMIT:
        raise ValueError("TAK package must be at most 10 MB")
    end = data.rfind(b"PK\x05\x06", max(0, len(data) - 65557))
    if end < 0 or end + 22 > len(data):
        raise ValueError("Invalid ZIP directory")
    disk, directory_disk, disk_entries, entries, length, offset, comment = (
        struct.unpack_from("<HHHHIIH", data, end + 4)
    )
    if (
        disk
        or directory_disk
        or disk_entries != entries
        or entries > 512
        or end + 22 + comment != len(data)
        or offset + length > end
    ):
        raise ValueError("Unsupported ZIP directory")
    position, count = offset, 0
    while position < offset + length:
        if position + 46 > end or data[position : position + 4] != b"PK\x01\x02":
            raise ValueError("Invalid ZIP entry")
        name, extra, item_comment = struct.unpack_from("<HHH", data, position + 28)
        position += 46 + name + extra + item_comment
        count += 1
        if count > 512 or position > offset + length:
            raise ValueError("Too many ZIP entries")
    if count != entries or position != offset + length:
        raise ValueError("ZIP entry count mismatch")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        if (
            len(entries) > 512
            or sum(entry.file_size for entry in entries) > 20 * 1024 * 1024
        ):
            raise ValueError("TAK package expands beyond limits")
        for entry in entries:
            if (
                entry.filename.startswith("/")
                or "\\" in entry.filename
                or ".." in entry.filename.split("/")
                or entry.flag_bits & 1
            ):
                raise ValueError("Unsafe or encrypted package entry")
        if "MANIFEST/manifest.xml" not in archive.namelist():
            raise ValueError("Package has no manifest")
        if archive.getinfo("MANIFEST/manifest.xml").file_size > 65536:
            raise ValueError("Package manifest too large")
        manifest = safe_xml(archive.read("MANIFEST/manifest.xml"))
        if manifest.tag != "MissionPackageManifest":
            raise ValueError("Invalid package manifest")


class TakWebClient:
    def __init__(self, host, port, context, username="", password=""):
        validate_host_port(host, port)
        if any(
            not isinstance(value, str) or len(value) > 1024
            for value in (username, password)
        ):
            raise ValueError("Invalid TAK credentials")
        self.origin = URL.build(scheme="https", host=host, port=port)
        self.context = context
        if ":" in username:
            raise ValueError("Invalid TAK username")
        self.authorization = (
            "Basic "
            + base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
            if username
            else None
        )

    async def request(
        self,
        method,
        path,
        *,
        params=None,
        data=None,
        headers=None,
        limit=65536,
        allow_missing=False,
    ):
        timeout = aiohttp.ClientTimeout(total=45, connect=15)
        headers = dict(headers or {})
        if self.authorization:
            headers["Authorization"] = self.authorization
        async with aiohttp.ClientSession(timeout=timeout, trust_env=False) as session:
            try:
                async with session.request(
                    method,
                    self.origin.with_path(path),
                    params=params,
                    data=data,
                    headers=headers,
                    ssl=self.context,
                    allow_redirects=False,
                ) as response:
                    if allow_missing and response.status == 404:
                        return None
                    if response.status < 200 or response.status >= 300:
                        raise ConnectionError(
                            f"TAK HTTPS request failed ({response.status})"
                        )
                    chunks, size = [], 0
                    async for chunk in response.content.iter_chunked(65536):
                        size += len(chunk)
                        if size > limit:
                            raise ValueError("TAK response exceeds size limit")
                        chunks.append(chunk)
                    return b"".join(chunks)
            except (aiohttp.ClientError, TimeoutError):
                raise ConnectionError(
                    "TAK HTTPS connection failed; check server and certificates"
                ) from None

    async def search(self, keywords=""):
        if not isinstance(keywords, str) or len(keywords) > 128:
            raise ValueError("Search is too long")
        raw = await self.request(
            "GET",
            "/Marti/api/sync/search",
            params={"keywords": keywords},
            limit=1024 * 1024,
        )
        if raw is None:
            raise ConnectionError("TAK search returned no response")
        result = json.loads(raw)
        if isinstance(result, dict):
            result = result.get("results", result.get("data", []))
            if isinstance(result, dict):
                result = result.get("results", [])
        if not isinstance(result, list):
            raise ValueError("Unsupported package search response")
        return [
            {
                "hash": row.get("hash", row.get("sha256", "")),
                "name": str(row.get("name", row.get("filename", "TAK package")))[:128],
            }
            for row in result[:200]
            if isinstance(row, dict)
            and HASH.fullmatch(str(row.get("hash", row.get("sha256", ""))))
        ]

    async def download(self, digest):
        if not isinstance(digest, str) or not HASH.fullmatch(digest):
            raise ValueError("Enter a SHA-256 package hash")
        raw = await self.request(
            "GET",
            "/Marti/api/sync/content",
            params={"hash": digest},
            limit=PACKAGE_LIMIT,
            allow_missing=True,
        )
        if raw is None:
            raw = await self.request(
                "GET",
                "/Marti/sync/content",
                params={"hash": digest},
                limit=PACKAGE_LIMIT,
            )
        if raw is None:
            raise ConnectionError("TAK download returned no response")
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("Downloaded package hash does not match")
        await asyncio.to_thread(validate_package, raw)
        return {
            "hash": digest,
            "zip_base64": base64.b64encode(raw).decode("ascii"),
            "bytes": len(raw),
        }

    async def upload(self, zip_base64, name, private=True):
        if (
            type(private) is not bool
            or not isinstance(name, str)
            or not name
            or len(name) > 128
            or any(c in name for c in "/\\\r\n\x00")
        ):
            raise ValueError("Invalid package filename or visibility")
        if not isinstance(zip_base64, str) or len(zip_base64) > (
            PACKAGE_LIMIT * 4 // 3 + 8
        ):
            raise ValueError("Package exceeds size limit")
        raw = base64.b64decode(zip_base64, validate=True)
        await asyncio.to_thread(validate_package, raw)
        digest = hashlib.sha256(raw).hexdigest()
        form = aiohttp.FormData()
        form.add_field(
            "assetfile", raw, filename=name, content_type="application/x-zip-compressed"
        )
        await self.request(
            "POST",
            "/Marti/sync/missionupload",
            params={
                "hash": digest,
                "filename": name,
                "creatorUid": "meshchat-next-" + str(uuid.uuid4()),
            },
            data=form,
        )
        # Server storage visibility is explicit; never broadcast a transfer announcement.
        await self.request(
            "PUT",
            f"/Marti/api/sync/metadata/{digest}/tool",
            data="private" if private else "public",
            headers={"Content-Type": "text/plain"},
        )
        return {
            "hash": digest,
            "bytes": len(raw),
            "private": private,
            "state": "uploaded",
        }


async def enroll(host, port, username, password, ca=""):
    if (
        not isinstance(username, str)
        or not username
        or len(username) > 128
        or any(ord(c) < 32 for c in username)
    ):
        raise ValueError("Enrollment requires a username")
    context = ssl.create_default_context(cadata=ca or None)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    web = TakWebClient(host, port, context, username, password)
    config = safe_xml(await web.request("GET", "/Marti/api/tls/config"))
    attributes = [x509.NameAttribute(NameOID.COMMON_NAME, username)]
    mapping = {
        "O": NameOID.ORGANIZATION_NAME,
        "OU": NameOID.ORGANIZATIONAL_UNIT_NAME,
        "C": NameOID.COUNTRY_NAME,
        "ST": NameOID.STATE_OR_PROVINCE_NAME,
        "L": NameOID.LOCALITY_NAME,
    }
    for node in config.iter():
        if node.tag.split("}")[-1].lower() not in ("entry", "nameentry"):
            continue
        name, value = node.get("name"), node.get("value")
        if name in mapping and value and len(value) <= 128:
            attributes.append(x509.NameAttribute(mapping[name], value))

    def generate():
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        csr = (
            x509.CertificateSigningRequestBuilder()
            .subject_name(x509.Name(attributes))
            .sign(key, hashes.SHA256())
        )
        return key, csr.public_bytes(serialization.Encoding.PEM)

    key, csr = await asyncio.to_thread(generate)
    signed = await web.request(
        "POST",
        "/Marti/api/tls/signClient",
        params={
            "clientUid": "meshchat-next-" + str(uuid.uuid4()),
            "version": "Meshchat neXt",
        },
        data=csr,
        headers={"Content-Type": "text/plain"},
        limit=1024 * 1024,
    )
    if signed is None:
        raise ConnectionError("TAK enrollment returned no certificate")
    certificates = []
    if b"-----BEGIN CERTIFICATE-----" in signed:
        certificates = x509.load_pem_x509_certificates(signed)
    else:
        for secret in (b"atakatak", None):
            try:
                _, cert, others = pkcs12.load_key_and_certificates(signed, secret)
                certificates = ([cert] if cert else []) + list(others or [])
                break
            except ValueError:
                continue
    public = key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    certificate = next(
        (
            cert
            for cert in certificates
            if cert.public_key().public_bytes(
                serialization.Encoding.DER,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            == public
        ),
        None,
    )
    now = datetime.datetime.now(datetime.UTC)
    if (
        certificate is None
        or not certificate.not_valid_before_utc <= now < certificate.not_valid_after_utc
    ):
        raise ValueError("Enrollment did not return a valid certificate for this key")
    common_names = certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    if len(common_names) != 1 or common_names[0].value != username:
        raise ValueError("Enrolled certificate has an unexpected account name")
    leaf = certificate.public_bytes(serialization.Encoding.PEM)
    chain = b"".join(
        cert.public_bytes(serialization.Encoding.PEM)
        for cert in certificates
        if cert != certificate
    )
    return {
        "certificate": (leaf + chain).decode("ascii"),
        "private_key": key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode("ascii"),
        "expires": certificate.not_valid_after_utc.isoformat(),
        "host": host,
        "ca": ca,
    }
