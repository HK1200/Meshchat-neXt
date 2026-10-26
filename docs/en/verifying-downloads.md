# Verifying Meshchat neXt builds

This is an unpublished local preview. There is no official neXt download site, release repository, update feed, or release signing identity yet. Do not treat upstream application signatures as signatures for this derivative.

For local review, compare artifacts with the SHA-256 inventory provided alongside the build. A matching checksum detects changed bytes; it does not establish a publisher identity. The Android preview is development-signed and installs under its own application ID, `com.haadkoe.meshchatnext`.

Before publication, select and securely back up a separate Android release key, Reticulum update signer, and any desktop signing identities. Configure the expected certificate and signer in the release verification job, then verify the final artifacts and signed update manifest. Strict source-inventory verification also requires a neXt-specific signer and a newly generated inventory.

Automatic update discovery is disabled until both `MESHCHATNEXT_UPDATE_BASE_URL` and `MESHCHATNEXT_UPDATE_SIGNER` are configured. Installing a future production-signed APK over this development preview may require an explicit backup and migration.
