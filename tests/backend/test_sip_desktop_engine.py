# SPDX-License-Identifier: MIT
import asyncio
import sys
from pathlib import Path

import pytest

from meshchatnext.src.backend.sip_desktop_engine import DesktopSipEngine

BINARY = Path(
    ".local/windows-sip/meshchatnext-sip.exe"
    if sys.platform == "win32"
    else ".local/linux-sip/meshchatnext-sip"
)
pytestmark = pytest.mark.skipif(
    not BINARY.is_file(), reason="Local native SIP build required"
)


@pytest.mark.asyncio
async def test_real_engine_concurrent_requests_and_shutdown():
    events = []
    engine = DesktopSipEngine(BINARY, test_audio=True, on_event=events.append)
    await asyncio.gather(engine.launch(), engine.launch())
    process = engine._process
    try:
        rows = await asyncio.gather(*(engine.command("ping") for _ in range(20)))
        assert len({r["id"] for r in rows}) == 20
        assert all(r["state"] == "ok" for r in rows)
        assert not engine._pending
        assert events[0]["state"] == "ready"
    finally:
        await engine.close()
    assert not engine.running and process.returncode == 0


@pytest.mark.asyncio
async def test_real_engine_invalid_start_does_not_leak_secret_or_register():
    events = []
    engine = DesktopSipEngine(BINARY, test_audio=True, on_event=events.append)
    await engine.launch()
    try:
        with pytest.raises(ValueError) as error:
            await engine.command(
                "start",
                user="bad;user",
                host="127.0.0.1",
                port=1,
                password="test-secret",
            )
        assert "test-secret" not in str(error.value)
        assert not any(e["state"] == "registering" for e in events)
        assert (await engine.command("ping"))["state"] == "ok"
        with pytest.raises(ValueError, match="too large"):
            await engine.command("start", password="x" * 5000)
        with pytest.raises(ValueError, match="Reserved"):
            await engine.command("ping", id="override")
    finally:
        await engine.close()


@pytest.mark.asyncio
async def test_real_engine_restart_and_callback_failure():
    def broken(event):
        raise RuntimeError("observer failure")

    engine = DesktopSipEngine(BINARY, test_audio=True, on_event=broken)
    await engine.launch()
    first = engine._process
    await engine.close()
    await engine.launch()
    try:
        assert engine._process is not first
        assert (await engine.command("ping"))["state"] == "ok"
    finally:
        await engine.close()
    assert first.returncode == 0


@pytest.mark.asyncio
async def test_actual_engine_closes_on_input_eof_without_hanging():
    p = await asyncio.create_subprocess_exec(
        str(BINARY.resolve()),
        "--test-audio",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    assert b"ready" in await asyncio.wait_for(p.stdout.readline(), 5)
    p.stdin.close()
    assert await asyncio.wait_for(p.wait(), 4) == 0


@pytest.mark.asyncio
async def test_actual_engine_rejects_oversized_frame_and_exits():
    p = await asyncio.create_subprocess_exec(
        str(BINARY.resolve()),
        "--test-audio",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    assert b"ready" in await asyncio.wait_for(p.stdout.readline(), 5)
    p.stdin.write(b"x" * 4097)
    await p.stdin.drain()
    assert b"protocol_error" in await asyncio.wait_for(p.stdout.readline(), 5)
    assert await asyncio.wait_for(p.wait(), 4) == 0


class LoopbackRegistrar(asyncio.DatagramProtocol):
    """Test-only UDP registrar, with no forwarding beyond localhost."""

    def __init__(self):
        self.contacts = {}
        self.unregistered = set()
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, address):
        import re

        text = data.decode("utf-8")
        lines = text.split("\r\n")
        if not lines[0].startswith("REGISTER "):
            return
        headers = {}
        for line in lines[1:]:
            if ":" in line:
                name, value = line.split(":", 1)
                headers[name.lower()] = value.strip()
        user = re.search(r"sip:([^@>]+)@", headers["from"]).group(1)
        self.contacts[user] = re.search(r"<([^>]+)>", headers["contact"]).group(1)
        contact_expiry = re.search(r";expires=(\d+)", headers["contact"])
        expiry = (
            contact_expiry.group(1)
            if contact_expiry
            else headers.get("expires", "3600")
        )
        if expiry == "0":
            self.unregistered.add(user)
        response = ["SIP/2.0 200 OK"]
        response.extend(
            f"{name}: {headers[name]}"
            for name in ("via", "from", "to", "call-id", "cseq", "contact")
        )
        response += [
            f"Expires: {expiry}",
            "Content-Length: 0",
            "",
            "",
        ]
        self.transport.sendto("\r\n".join(response).encode(), address)


async def wait_state(events, state, timeout=6):
    async with asyncio.timeout(timeout):
        while not any(row["state"] == state for row in events):
            await asyncio.sleep(0.02)


@pytest.mark.asyncio
async def test_real_two_endpoint_loopback_call_requires_explicit_answer():
    loop = asyncio.get_running_loop()
    registrar = LoopbackRegistrar()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: registrar, local_addr=("127.0.0.1", 0)
    )
    port = transport.get_extra_info("sockname")[1]
    left_events, right_events = [], []
    left = DesktopSipEngine(BINARY, test_audio=True, on_event=left_events.append)
    right = DesktopSipEngine(BINARY, test_audio=True, on_event=right_events.append)
    try:
        await asyncio.gather(left.launch(), right.launch())
        await left.command(
            "start",
            user="next_test_a",
            host="127.0.0.1",
            port=port,
            password="local-only",
        )
        await right.command(
            "start",
            user="next_test_b",
            host="127.0.0.1",
            port=port,
            password="local-only",
        )
        await asyncio.gather(
            wait_state(left_events, "registered"),
            wait_state(right_events, "registered"),
        )
        await left.command("dial", peer=registrar.contacts["next_test_b"])
        await wait_state(right_events, "incoming")
        await asyncio.sleep(0.15)
        assert not any(row["state"] == "connected" for row in right_events)
        await right.command("answer")
        await asyncio.gather(
            wait_state(left_events, "connected"), wait_state(right_events, "connected")
        )
        async with asyncio.timeout(6):
            while True:
                left_stats, right_stats = await asyncio.gather(
                    left.command("stats"), right.command("stats")
                )
                if all(
                    row["sent"] > 0 and row["received"] > 0
                    for row in (left_stats, right_stats)
                ):
                    break
                await asyncio.sleep(0.1)
        await left.command("mute", value=True)
        await left.command("mute", value=False)
        await left.command("digit", digit="5")
        await left.command("hangup")
        await asyncio.gather(
            wait_state(left_events, "ended"), wait_state(right_events, "ended")
        )
    finally:
        await asyncio.gather(left.close(), right.close())
        transport.close()
    assert registrar.unregistered == {"next_test_a", "next_test_b"}


class DigestRegistrar(LoopbackRegistrar):
    def __init__(self):
        super().__init__()
        self.authenticated = 0

    def datagram_received(self, data, address):
        import hashlib
        import re

        text = data.decode()
        headers = {
            line.split(":", 1)[0].lower(): line.split(":", 1)[1].strip()
            for line in text.split("\r\n")[1:]
            if ":" in line
        }
        auth = headers.get("authorization", "")
        code = 401
        if auth:
            fields = {
                key: quoted or bare
                for key, quoted, bare in re.findall(
                    r'(\w+)=(?:"([^"]*)"|([^,\s]+))', auth
                )
            }

            def md5(value):
                return hashlib.md5(value.encode(), usedforsecurity=False).hexdigest()

            first = md5(f"{fields.get('username')}:next-test:local-password")
            second = md5(f"REGISTER:{fields.get('uri')}")
            expected = md5(
                f"{first}:test-nonce:{fields.get('nc')}:{fields.get('cnonce')}:auth:{second}"
            )
            if fields.get("response") == expected and fields.get("qop") == "auth":
                self.authenticated += 1
                return super().datagram_received(data, address)
            code = 403
        response = [
            f"SIP/2.0 {code} " + ("Unauthorized" if code == 401 else "Forbidden")
        ]
        response.extend(
            f"{name}: {headers[name]}"
            for name in ("via", "from", "to", "call-id", "cseq")
        )
        if code == 401:
            response.append(
                'WWW-Authenticate: Digest realm="next-test", nonce="test-nonce", algorithm=MD5, qop="auth"'
            )
        response += ["Content-Length: 0", "", ""]
        self.transport.sendto("\r\n".join(response).encode(), address)
        return None


@pytest.mark.asyncio
@pytest.mark.parametrize("correct_password", [True, False])
async def test_actual_native_digest_authentication(correct_password):
    registrar = DigestRegistrar()
    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: registrar, local_addr=("127.0.0.1", 0)
    )
    events = []
    engine = DesktopSipEngine(BINARY, test_audio=True, on_event=events.append)
    try:
        await engine.launch()
        await engine.command(
            "start",
            user="next_digest",
            host="127.0.0.1",
            port=transport.get_extra_info("sockname")[1],
            password="local-password" if correct_password else "wrong-password",
        )
        await wait_state(
            events, "registered" if correct_password else "registration_failed"
        )
        if correct_password:
            assert registrar.authenticated >= 1
        else:
            assert any(row.get("code") == 403 for row in events)
        assert "local-password" not in str(events) and "wrong-password" not in str(
            events
        )
    finally:
        await engine.close()
        transport.close()
    if correct_password:
        assert registrar.unregistered == {"next_digest"}
