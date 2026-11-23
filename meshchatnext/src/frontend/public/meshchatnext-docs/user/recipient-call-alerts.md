# Optional incoming-call alerts for iPhone and iPad contacts

This is development functionality. Live Apple push delivery has not been qualified. It requires a compatible provider and a correctly signed recipient app with Apple push capabilities. It does not add background SIP support to a provider that lacks it.

A recipient explicitly enables incoming Reticulum call alerts on their device and shares their provider's HTTPS address and audience. In neXt, open **Settings → neXt Family → Optional recipient call alerts**, choose that saved messaging contact, and enter those two details. neXt obtains the contact's public identity from their announce; you do not need to type their public key. If the identity is unavailable, receive their announce and refresh the contact list. Saving the route sends no request to the provider.

When you call that contact, neXt sends a short signed request to the configured provider before looking for the ordinary Reticulum voice path. The provider receives public caller/recipient identifiers, a random call identifier and a timestamp. Neither microphone audio nor message text is sent to the alert provider. The normal Reticulum call carries the audio. The recipient still applies their own saved caller permissions.

Ending or cancelling the call sends an ordered signed cancellation, including when the first provider response was lost. A failed alert request does not prevent ordinary calls. These requests are bounded and best effort; they are not a guarantee of delivery.

Use **Remove recipient call alerts** to remove only these optional details. Deleting the contact or changing its messaging address also removes its route. Switching identities keeps routes separate. No Apple token, recipient enrollment code or SIP password belongs in this sender-side form.
