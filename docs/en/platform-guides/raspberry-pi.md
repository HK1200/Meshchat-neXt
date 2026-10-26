# Raspberry Pi headless setup

This guide shows a simple headless setup for running Meshchat neXt on a Raspberry Pi 4
with a web UI you can access from another device on your network.

This install path uses a release wheel, which already includes frontend assets.

## Automated Setup Scripts

```bash
# Use scripts/rpi/install_meshchatnext.sh from the reviewed local checkout.
```

If you have the repo cloned locally already:

```bash
bash scripts/rpi/install_meshchatnext.sh
```

The installer guides you through:

- Optional espeak-ng install (tries apt/dnf/pacman)
- Install method (pipx or venv + pip)
- Wheel choice (latest stable, latest pre-release, or a custom URL)
- Optional **cosign** attestation: if a *.whl.cosign.bundle is published
  next to the wheel, you can verify it. The script uses cosign on PATH if
  present, or downloads a **checksum-verified** official Linux binary to /tmp
  (the Sigstore bundle format is not reimplemented in shell, so you still use the
  real cosign to verify, without installing a distro package)
- Storage and Reticulum directories
- Bind host and port (with availability check)
- HTTPS on/off (default on)
- Service mode (system, user, or none)
- Service startup validation via the HTTP status endpoint

If startup validation fails, it prints recent logs and stops the service to avoid
restart loops.

## 1) Install Base Dependencies

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y python3 python3-pip pipx
```

## 2) Enable pipx Path

```bash
pipx ensurepath
source ~/.profile
```

If pipx is not available in your distro package repo, install it with:

```bash
python3 -m pip install --user pipx
python3 -m pipx ensurepath
source ~/.profile
```

## 3) Install Meshchat neXt with pipx (recommended)

Preferred option (recommended): install from a release wheel,
because the wheel bundles frontend assets.

```bash
pipx install /path/to/meshchat_next-<version>-py3-none-any.whl
```

Direct example (replace X.Y.Z with the release you want):

```bash
# Use a reviewed local artifact; publication is not configured.
```

py3-none-any wheels are architecture-independent, so the same wheel artifact
works on Raspberry Pi ARM and x86_64 Linux systems.

Upgrade example:

```bash
pipx upgrade meshchatnext
```

## 4) Install Meshchat neXt without pipx (venv + pip)

If you prefer not to use pipx:

```bash
mkdir -p ~/meshchatnext
cd ~/meshchatnext
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
Use the reviewed local Meshchat neXt APK or wheel. This preview has no public download feed.
```

Run command in venv mode:

```bash
~/meshchatnext/.venv/bin/meshchatnext --headless --host 0.0.0.0 --port 8000
```

## 5) Run Meshchat neXt (Headless)

```bash
meshchatnext --headless --host 0.0.0.0 --port 8000
```

Then open:

```bash
http://<pi-ip>:8000
```

## 6) Configure a systemd Service

systemd keeps Meshchat neXt running in the background and starts it automatically
on boot.

You have two service styles:

- System service (/etc/systemd/system/...) for always-on host services.
- User service (~/.config/systemd/user/...) for per-user sessions.

### Option A: System service (recommended for Pi node/server use)

Create /etc/systemd/system/meshchatnext.service:

```ini
[Unit]
Description=Meshchat neXt Headless (system service)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
Group=pi
WorkingDirectory=/home/pi/meshchatnext
Environment="PATH=/home/pi/.local/bin:/usr/bin:/bin"
ExecStart=/home/pi/.local/bin/meshchatnext --headless --host 0.0.0.0 --port 8000 --storage-dir /home/pi/meshchatnext/storage --reticulum-config-dir /home/pi/.reticulum
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

The above service file is for pipx installs. For venv installs, use:

```ini
[Service]
Type=simple
User=pi
Group=pi
WorkingDirectory=/home/pi/meshchatnext
Environment="PATH=/home/pi/meshchatnext/.venv/bin:/usr/bin:/bin"
ExecStart=/home/pi/meshchatnext/.venv/bin/meshchatnext --headless --host 0.0.0.0 --port 8000 --storage-dir /home/pi/meshchatnext/storage --reticulum-config-dir /home/pi/.reticulum
Restart=always
RestartSec=3
```

Update User, Group, and paths if your install location is different.

Enable and start:

```bash
mkdir -p /home/pi/meshchatnext/storage /home/pi/.reticulum
sudo chown -R pi:pi /home/pi/meshchatnext
sudo systemctl daemon-reload
sudo systemctl enable --now meshchatnext.service
sudo systemctl status meshchatnext.service
```

### Option B: User service (no sudo system unit)

Create ~/.config/systemd/user/meshchatnext.service:

```ini
[Unit]
Description=Meshchat neXt Headless (user service)
After=network-online.target

[Service]
Type=simple
WorkingDirectory=%h/meshchatnext
Environment="PATH=%h/.local/bin:/usr/bin:/bin"
ExecStart=%h/.local/bin/meshchatnext --headless --host 0.0.0.0 --port 8000 --storage-dir %h/meshchatnext/storage --reticulum-config-dir %h/.reticulum
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
```

Enable/start user service:

```bash
systemctl --user daemon-reload
systemctl --user enable --now meshchatnext.service
systemctl --user status meshchatnext.service
```

If you want user services to stay active without login:

```bash
sudo loginctl enable-linger pi
```

### Service management commands

```bash
sudo systemctl restart meshchatnext.service
sudo systemctl stop meshchatnext.service
sudo systemctl disable meshchatnext.service
```

## Low-memory and SD card tuning

These settings matter most on multi-core boards (Pi 3, 4, 5, Zero 2 W)
running a 64-bit OS. The install script already writes them into the
generated systemd units.

- MALLOC_ARENA_MAX=2 caps the number of glibc malloc arenas. The default
  scales with CPU core count (8 per core on 64-bit), which wastes tens of
  megabytes of RAM in a threaded Python process. Two arenas is plenty for
  this workload.
- OPENBLAS_NUM_THREADS=1 keeps the OpenBLAS copy bundled with numpy from
  spawning one worker thread per CPU core. Meshchat neXt only uses numpy for
  small audio codec buffers, which never benefit from BLAS threading.
- MESHCHAT_LOG_DB=0 stops writing debug logs into the SQLite database.
  Logs stay in the in-memory ring buffer, which avoids a steady stream of
  small WAL writes to the SD card. Leave it enabled if you want the debug
  log viewer to keep working across restarts.

If you wrote the service file by hand, add the variables like this:

```ini
[Service]
Environment="MALLOC_ARENA_MAX=2"
Environment="OPENBLAS_NUM_THREADS=1"
Environment="MESHCHAT_LOG_DB=0"
```

Then reload and restart:

```bash
sudo systemctl daemon-reload
sudo systemctl restart meshchatnext.service
```

Useful logs and troubleshooting:

```bash
journalctl -u meshchatnext.service -f
journalctl -u meshchatnext.service -n 200 --no-pager
systemctl show meshchatnext.service -p ExecStart -p User -p Group
```

## Reset Password

If you forget the web UI password and have SSH access to the Pi, reset it with the --reset-password flag:

```bash
meshchatnext --reset-password --headless --host 0.0.0.0 --port 8000
```

Or set the environment variable:

```bash
MESHCHAT_RESET_PASSWORD=true meshchatnext --headless --host 0.0.0.0 --port 8000
```

This clears the stored password hash on startup. Open the web UI and you will see the Initial Setup screen where you can set a new password. After resetting, you can stop the app and restart without the flag.

## Notes

- Reticulum configuration and identity data are stored in the service user's home
  directory by default (for example ~/.reticulum and Meshchat neXt storage paths).
- If you attach RNode hardware by USB, make sure the service user has permission
  to access serial devices (dialout group on Debian-based systems).
