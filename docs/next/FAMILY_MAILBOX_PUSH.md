# Family mailbox push hints

To send alerts to Family devices that opted in through a private provider, add
`mailbox-push-routes.json` beside `database.db` in the sending neXt identity's
storage directory. Each recipient needs an explicit entry.

```json
{
  "<recipient LXMF address in lowercase hex>": {
    "provider": "https://alerts.example.org",
    "audience": "operator-supplied provider name",
    "relay": "<LXMF propagation node address in lowercase hex>"
  }
}
```

Set the same relay as the preferred propagation node in neXt and use
**Propagated** delivery or the existing fallback to that node. The receiver's
guardian needs to approve the sending key and opt in on the provider.

neXt sends the signed hint after LXMF reports propagation success and only
when the destination on the proven link matches the configured relay. The
HTTPS provider receives the recipient address, encrypted packet hash, sender
public key, timestamp, and signature. The message body and attachments stay
in LXMF. Provider errors leave LXMF delivery intact.
