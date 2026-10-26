# SPDX-License-Identifier: MIT
"""OS alert delivery is independent of the MeshCore radio receive worker."""

import asyncio


def notification_text(event):
    label = str(
        event.get("name")
        or ("Channel" if event["kind"] == "channel" else "Direct message")
    )
    text = str(event.get("text") or "New message")
    prefix, separator, body = (
        text.partition(": ") if event["kind"] == "channel" else ("", "", text)
    )
    if not separator:
        body = text
    if body.startswith(("VE3:", "VI1:")):
        try:
            from meshchatnext.src.backend.meshcore_voice import envelope

            meta = envelope(body)
            label_text = (
                "Photo"
                if meta["mode"] == 40
                else f"Voice clip · {meta['seconds']} seconds"
            )
            caption = body.partition(" ")[2]
            text = (
                (prefix + ": " if separator else "")
                + label_text
                + (" · " + caption if caption else "")
            )
        except ValueError:
            pass
    return f"MeshCore · {label}"[:200], text[:200]


async def deliver_notification(owner, event):
    from meshchatnext.android_push_bridge import (
        _dnd_enabled,
        _is_open_conversation,
        _notify_java,
    )

    dnd = False
    try:
        dnd = bool(owner.config.do_not_disturb_enabled.get())
    except AttributeError:
        pass
    key = event["notification_key"]
    if not dnd and not _dnd_enabled() and not _is_open_conversation(key):
        title, body = notification_text(event)
        await asyncio.to_thread(_notify_java, title, body, event["id"], key)
    await owner.websocket_broadcast(event)
