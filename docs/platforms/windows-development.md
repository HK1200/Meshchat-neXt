# Windows 11 port — local development

This is work in progress, not a Windows release. No Windows package has been built or verified yet. Source is isolated in `work/meshchat-next-windows`, branch `feature/windows11-port`, based on a4cfc10. The separate Radio2/channel branch is preserved; it has not been merged here.

## First implementation

- MeshCore USB: explicit COM1–COM65535 candidates; device enumeration before opening; no arbitrary file/device paths. COM names are normalised and duplicate radio claims are case-insensitive.
- MeshCore Bluetooth: reuse Bleak's native Windows backend and Bluetooth addresses. Connections remain independent and reconnect through the existing companion lifecycle. Actual Windows adapter behaviour remains untested.
- Saved MeshCore node passwords: Windows Credential Manager generic credentials, isolated by application/owner/peer/role, current-user/local-computer persistence. No plaintext file fallback, credential enumeration or Windows account-password changes. Presence checks do not copy secret content into Python. Native buffers used for writes are cleared afterward.
- NSIS installer output includes architecture so x64 and ARM64 files cannot overwrite each other.

## Native session

Use this computer's existing Windows 11 dual boot for hardware validation. A VM can later help with clean install/update snapshots but cannot replace final tests against the actual Bluetooth adapter, USB radios and audio drivers.

Do not reboot until the Linux work is checkpointed and a Windows-readable source handoff is prepared. The active Linux workspace is inside an ext4 image: Windows must use a separate exported working folder on the Shared SSD, not the mounted Linux checkout. Keep temporary files and dependency caches on that SSD. Never include private signing keys, migrated phone profiles, saved identities or live test databases in the handoff. No signing or publication is part of this local phase.

Before builds, review pinned native dependencies, Windows Python/Node architecture, USB drivers, native Codec2/AV1 availability and frozen-module inclusion. Use the existing CI Windows build recipe as the starting point; do not pretend a Linux cx_Freeze output is a Windows binary. Source-integrity manifests must be regenerated through the normal approved signing process for a reviewed candidate; do not bypass verification to get a preview booting.

After setting up the native dependency environment, run `python scripts/windows/check-platform.py` first. It lists serial candidates without opening them. Optional `--scan-bluetooth` scans UART-service advertisements without connecting. Optional `--credential-self-test` creates, reads and removes one random test credential; it does not touch saved app slots. Keep the output local.

Then test two distinct MeshCore radios: USB/USB and USB/Bluetooth, independent receive/reconnect, unplug/replug, Bluetooth power loss, per-owner history and sending-radio choice. Preserve the normal phone connections, identities, radio configuration and queued messages. Verify Reticulum/RNode remains independent.

## Native implementation awaiting Windows validation

Windows SIP implementation is now prepared for native compilation: inherited-pipe polling, WASAPI, OS DNS, explicit adapter-index/local-IP selection, per-socket outbound interface and datagram receive filters, Windows account credentials, backend lifecycle and desktop call UI. The shared helper compiled on Linux and its real IPC/authentication regressions pass there. The Windows branch has NOT been compiled or run yet. Build it before any native SIP availability claim.

Speaker echo cancellation on Windows is not verified or guaranteed. The Windows path does not invoke pactl or alter system defaults. Use a headset for the first call, then test speakers separately; implement/test native echo processing if needed. Linux Pulse/PipeWire cancellation remains unchanged.

Windows updates need a verified installer handoff and signing/trust policy, cancellation/retry and in-place data-preservation checks. Current Electron application of staged payloads supports AppImage only.

Still required on actual Windows: frozen startup/security checks, Credential Manager round-trip, USB/Bluetooth multi-radio tests, microphone/speaker and calls, notifications, offline MBTiles import, map/visualiser behaviour, backup/restore, and signed installer/update tests. x64 first; ARM64 needs matching native Python/dependencies and separate verification.

Primary references: [Windows generic credentials](https://learn.microsoft.com/windows/win32/api/wincred/ns-wincred-credentialw), [Bleak Windows backend](https://bleak.readthedocs.io/en/stable/backends/windows.html), [Baresip modules](https://github.com/baresip/baresip/wiki/Modules).


## First dual-boot test commands

Use the exported `source` folder on the Shared SSD, in an x64 Native Tools Command Prompt/PowerShell with MSVC, Windows SDK, CMake and Ninja. Python is pinned to 3.14, Node to 24+, pnpm to 12.7.0 and UV to 0.11.15 in the existing CI configuration. Check what is already installed before installing anything.

Dot-source `scripts/windows/media-env.ps1` in PowerShell first. It keeps all caches/temp under the handoff on the SSD. Then install the locked environment with `uv sync --frozen --group dev --extra meshcore`; do not weaken dependencies or signature checks to bypass failures.

Build only the helper first: `uv run --frozen python scripts/build-windows-sip.py --source-cache ../sip-sources`. The script checks all four source hashes, applies the documented socket-policy compile shim, and builds locally via CMake/Ninja. It does not register accounts or place calls.

Run `uv run --frozen python scripts/windows/check-platform.py --credential-self-test --scan-bluetooth --sip-ipc-test`. Then `uv run --frozen python -m pytest tests/backend/test_meshcore_windows.py tests/backend/test_sip_windows.py tests/backend/test_sip_desktop_engine.py --basetemp=temp-tests/windows-native -q -rs`. Native SIP tests use only loopback test accounts/registrars; no call to either phone. Do not count missing-helper skips as passes.

Verify the current pinned source signature before full app tests. Rebuild the frontend, frozen backend and package from that exact source; source integrity does not substitute for Windows Authenticode signing. Keep private signing keys on Linux. Windows binary publication remains held for signing and final native package/runtime checks.


## Local x64 native results — 2026-10-28

The exported SSD working copy has now compiled the real Windows SIP helper with
MSVC 19.44 and Windows SDK 10.0.26100, using the four checksum-pinned sources.
The native linker recipe now uses Baresip's actual `libbaresip.lib` output.

On Windows 11 x64 / Python 3.14.5, the readiness probe passed temporary Credential
Manager save/read/delete, serial enumeration, BLE discovery and 20 private helper
IPC pings with clean shutdown. No radio connections were opened. The focused
Windows backend/native-helper suite passed all 43 tests without skips, including
synthetic loopback registration, digest authentication and calls. An additional
30 desktop SIP/backend test-harness checks passed. Six focused frontend files
passed all 60 tests. Ruff passed on the modified Python test/support files.

The test harness required a Windows fix: `os.kill(pid, 0)` is not a safe liveness
probe there, so Windows now uses `psutil.pid_exists`, covered by three regression
tests. PulseAudio tests explicitly simulate Linux, and POSIX permission-bit
assertions run only on POSIX while password-isolation assertions run everywhere.
The case-colliding component test is now `FirstLaunchSetupComponent.test.js`.

These are local native development results. Speaker/microphone hardware, echo
cancellation, multi-radio USB/BLE receive/reconnect, full frozen app startup,
installer/update preservation and ARM64 remain unverified. The exported release
integrity manifest is still stale for local changes. Owner review and the normal
signed local candidate remain required before full packaged app validation.
No live SIP accounts, phone calls, firmware changes, publication or release were
part of these checks. See the handoff's `WINDOWS-NATIVE-RESULTS.txt` for details.


## Consolidated source status — 2026-10-29

The shared source now includes the Android usability preview changes: sidebar
destination dismissal, visible reorder Save/Cancel controls, onboarding Back,
channel notification selectors/unread totals, and SIP registration retry policy.
Windows native results above apply to their recorded candidates. The later SIP
candidate also passed strict source verification, frozen runtime/Opus checks,
48 active self-checks, registration and owner-confirmed two-way audio. It predates
this consolidated source; a new native Windows rebuild and runtime check remain
required before distributing the updated Windows build.

Windows Authenticode signing is pending the owner's SignPath application.
No Windows executable is represented as signed or ready for public release.
Keep signing private keys and live app profiles out of source and build handoffs.
Forced AppContainer runtime, signed installer/update preservation and Windows
ARM64 remain separate unverified gates. The existing Android/Linux releases and
update feeds are unchanged by this source update.


## Release preparation — 0.1.4

Android and Linux 0.1.4 are being prepared with the shared usability changes. Windows source remains part of the repository, while public Windows binaries remain withheld pending SignPath signing and final verification. CI build artifacts are test candidates, not signed public Windows releases.
