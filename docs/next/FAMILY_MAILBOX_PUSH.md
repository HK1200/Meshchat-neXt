# Family mailbox push hints

To send alerts to a Family device whose guardian has opted in, open **Settings →
neXt Family → Optional recipient alerts**. Search your saved Reticulum contacts,
select the recipient and enter the HTTPS provider, audience and propagation-node
address supplied by their guardian. Save explicitly to enable the route.
**Remove recipient alerts** turns it off for that contact; deleting the contact
or changing its messaging address also revokes the old route.

The provider is optional and needs to be configured by its operator. This
setting does not create a provider or enroll the receiving device. Use the same
relay as the recipient’s mailbox and your preferred propagation node.

Advanced users may also place `mailbox-push-routes.json` beside `database.db` in
the sending identity’s storage directory. Each recipient needs an explicit entry.

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
