# SPDX-License-Identifier: MIT
"""Debug-only radio checks. Messaging writes require an explicit test opt-in."""

import asyncio
import json

from meshchatnext.src.backend.meshcore_session import MeshCoreSession
from meshchatnext.src.backend.meshcore_transport import scan_ble


def discover(context):
    return json.dumps(asyncio.run(scan_ble(context)))


async def _coexist(context, target, seconds):
    from java import jclass

    log = jclass("android.util.Log")
    session = MeshCoreSession()
    queries = 0
    try:
        await session.connect("ble", target, context=context)
        initial = await session.read_settings()
        model = session._device_info.get("model", "")
        version = session._device_info.get("ver", "")
        log.i("MeshCoreCoexistenceTest", "phase=connected")
        for cycle in range(2):
            end = asyncio.get_running_loop().time() + seconds / 2
            while asyncio.get_running_loop().time() < end:
                await session.query_device()
                queries += 1
                await asyncio.sleep(1)
            if cycle == 0:
                await session.disconnect()
                log.i("MeshCoreCoexistenceTest", "phase=meshcore_closed")
                await asyncio.sleep(2)
                await session.connect("ble", target, context=context)
                log.i("MeshCoreCoexistenceTest", "phase=meshcore_reconnected")
        final = await session.read_settings()
        if final != initial:
            raise AssertionError("Read-only coexistence check changed radio settings")
        return {
            "status": "ok",
            "model": model,
            "version": version,
            "queries": queries,
            "reconnect": True,
            "settings_unchanged": True,
        }
    finally:
        await session.disconnect()
        log.i("MeshCoreCoexistenceTest", "phase=finished")


def coexist(context, target, seconds=20):
    if not 4 <= seconds <= 60:
        raise ValueError("Test duration must be 4-60 seconds")
    return json.dumps(asyncio.run(_coexist(context, target, seconds)))


class RNodeProbe:
    """Use RNS's actual Android BLE transport, querying firmware only (no LoRa writes)."""

    def __init__(self, context, address):
        import queue
        import threading

        from java import jclass
        from RNS.Interfaces.Android.RNodeInterface import BLEConnection

        jclass("org.able.BLE").setAppContext(context)
        adapter = jclass("android.bluetooth.BluetoothAdapter").getDefaultAdapter()
        paired = {
            str(item.getAddress()).upper()
            for item in adapter.getBondedDevices().toArray()
        }
        if address.upper() not in paired:
            raise ValueError("Explicit RNode target must already be paired")
        self.ble_rx_queue = b""
        self.ble_tx_queue = b""
        self.ble_rx_lock = threading.Lock()
        self.ble_tx_lock = threading.Lock()
        self.hw_errors = []
        self.awaiting_ble_reset = False
        self.port = "ble://" + address
        self.incoming = queue.Queue(maxsize=256)
        self.link = BLEConnection(owner=self, target_bt_addr=address)

    def ble_waiting(self):
        with self.ble_tx_lock:
            return bool(self.ble_tx_queue)

    def get_ble_waiting(self, maximum):
        with self.ble_tx_lock:
            result = self.ble_tx_queue[:maximum]
            self.ble_tx_queue = self.ble_tx_queue[maximum:]
            return result

    def ble_receive(self, data):
        self.incoming.put_nowait(bytes(data))

    async def ready(self):
        end = asyncio.get_running_loop().time() + 18
        while not self.link.is_open:
            if asyncio.get_running_loop().time() > end or self.hw_errors:
                raise ConnectionError("RNode BLE did not become ready")
            await asyncio.sleep(0.1)

    async def query(self):
        import queue

        if not self.link.is_open:
            raise ConnectionError("RNode link is disconnected")
        self.link.write(
            b"\xc0\x50\x00\xc0"
        )  # KISS CMD_FW_VERSION, same read-only query as RNS detect().
        end = asyncio.get_running_loop().time() + 8
        frame = bytearray()
        escaped = False
        while asyncio.get_running_loop().time() < end:
            try:
                data = await asyncio.to_thread(self.incoming.get, True, 0.2)
            except queue.Empty:
                continue
            for byte in data:
                if byte == 0xC0:
                    if len(frame) >= 3 and frame[0] == 0x50:
                        return list(frame[1:3])
                    frame.clear()
                    escaped = False
                elif escaped:
                    frame.append({0xDC: 0xC0, 0xDD: 0xDB}.get(byte, byte))
                    escaped = False
                elif byte == 0xDB:
                    escaped = True
                elif len(frame) < 4096:
                    frame.append(byte)
                else:
                    raise ConnectionError("RNode frame too large")
        raise TimeoutError("RNode firmware query timed out")

    async def close(self):
        self.link.cleanup()
        await asyncio.to_thread(self.link.close)
        await asyncio.to_thread(self.link.close_gatt)
        # RNS's daemon connection job checks should_run once per second.
        await asyncio.sleep(1.1)


async def _same_process(context, meshcore_address, rnode_address):
    node = None
    mesh = MeshCoreSession()
    try:
        node = RNodeProbe(context, rnode_address)
        await node.ready()
        before = await node.query()
        await mesh.connect("ble", meshcore_address, context=context)
        original = await mesh.read_settings()
        model = mesh._device_info.get("model", "")
        for _ in range(3):
            await asyncio.gather(mesh.query_device(), node.query())
        await mesh.disconnect()
        after_mesh_close = await node.query()
        if before != after_mesh_close:
            raise AssertionError("RNode firmware query changed after closing MeshCore")
        await mesh.connect("ble", meshcore_address, context=context)
        await node.close()
        node = None
        await mesh.query_device()
        if await mesh.read_settings() != original:
            raise AssertionError("MeshCore settings changed during coexistence test")
        return {
            "status": "ok",
            "same_process": True,
            "rnode_transport": "RNS Android BLEConnection",
            "rnode_firmware": before,
            "meshcore_model": model,
            "rnode_survived_meshcore_close": True,
            "meshcore_survived_rnode_close": True,
            "settings_unchanged": True,
        }
    finally:
        try:
            if node is not None:
                await node.close()
        finally:
            await mesh.disconnect()


def same_process(context, meshcore_address, rnode_address):
    return json.dumps(
        asyncio.run(_same_process(context, meshcore_address, rnode_address))
    )


async def _messaging(context, target, peer_name, seconds, send):
    import time
    import uuid
    from pathlib import Path

    from java import jclass

    from meshchatnext.src.backend.meshcore_messaging import MeshCoreMessaging
    from meshchatnext.src.backend.meshcore_store import MeshCoreStore

    log = jclass("android.util.Log")
    session = MeshCoreSession()
    store = await asyncio.to_thread(
        MeshCoreStore, Path(str(context.getFilesDir())) / "meshcore-messages.sqlite"
    )
    messenger = MeshCoreMessaging(session, store)
    baseline = None
    try:
        await session.connect("ble", target, context=context)
        baseline = await session.read_settings()
        await messenger.open()
        contacts = await messenger.sync_contacts()
        peers = [
            row
            for row in contacts
            if row["active"]
            and row["kind"] == 1
            and peer_name.casefold() in row["name"].casefold()
        ]
        if len(peers) != 1:
            raise AssertionError("Test peer must match exactly one chat contact")
        peer = peers[0]["peer"]
        result = {
            "contacts": len(contacts),
            "test_peer_found": True,
            "sent": False,
            "delivered": False,
            "received": False,
        }
        if send:
            started = time.time()
            request_id = uuid.uuid4().hex
            token = request_id[:6]
            await messenger.start_receiving()
            row = await messenger.send_direct(
                peer,
                f"Meshchat neXt connection test {token}. Please reply to confirm.",
                request_id=request_id,
            )
            result["sent"] = row["state"] in ("accepted", "delivered")
            log.i("MeshCoreMessagingTest", "phase=submitted")
            deadline = asyncio.get_running_loop().time() + seconds
            reported = False
            while asyncio.get_running_loop().time() < deadline:
                history = await messenger.history(peer)
                sent = next((row for row in history if row["id"] == request_id), None)
                result["delivered"] = sent is not None and sent["state"] == "delivered"
                result["received"] = any(
                    row["direction"] == "in" and row["created"] >= started
                    for row in history
                )
                if result["delivered"] and not reported:
                    log.i("MeshCoreMessagingTest", "phase=delivery_confirmed")
                    reported = True
                if result["delivered"] and result["received"]:
                    break
                await asyncio.sleep(1)
            result["outgoing_state"] = sent["state"] if sent else "missing"
            # Read via a newly opened database, proving history is durable.
            reopened = await asyncio.to_thread(MeshCoreStore, store.path)
            history = await asyncio.to_thread(reopened.history, messenger.owner, peer)
            result["history_persisted"] = any(
                row["id"] == request_id for row in history
            )
        result["settings_unchanged"] = await session.read_settings() == baseline
        if not result["settings_unchanged"]:
            raise AssertionError("Messaging changed radio settings")
        result["status"] = "ok"
        return result
    finally:
        await messenger.close()


def messaging(context, target, peer_name, seconds=90, send=False):
    """Explicit opt-in sends one benign test DM; keeps private history on the phone."""
    if not peer_name or not 1 <= seconds <= 120:
        raise ValueError("Test requires a named peer and a bounded receive window")
    return json.dumps(
        asyncio.run(_messaging(context, target, peer_name, seconds, send))
    )
