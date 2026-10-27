# Linux installation, radios and updates

## Install and use neXt on Linux

The Linux desktop build brings the independent Reticulum, MeshCore and SIP services to 64-bit Intel/AMD computers. The initial supported target is Linux Mint 22 or Ubuntu 24.04 and newer; an Android x86_64 APK is not a Linux package.

1. Download the Linux amd64 .deb for your system package installer, or the x86_64 .AppImage for a portable application. Keep the checksum file from the same release. ARM Linux, 32-bit Linux and other distributions are not covered by this initial build.
2. For the .deb, open it with your system package installer and approve installation. Launch Meshchat neXt from the application menu. For AppImage, save it in a writable folder you own, allow running it as a program in file properties, then open it. Do not run neXt as root or disable its sandbox.
3. Close the other desktop copy before starting a replacement. Back up your existing identity and messages first. Keep the same data folder to retain your setup; Android backups and other apps may cover only supported fields, not complete history.
4. Choose the services you want in first-start setup. Reticulum internet TCP offers rmap.world:4242; MeshCore needs its own companion. RNode and MeshCore may run together through separate connections. Close other apps holding the same USB port or Bluetooth device.
5. For USB use a data cable, refresh devices and choose the correct radio. If Linux denies serial access, grant your user the distribution’s serial-device group permission and sign out/in; do not make the port world-writable. For MeshCore BLE, enable the system Bluetooth service, close the phone connection and refresh/select the companion in neXt.
6. For SIP, use Settings → SIP and your own provider credentials. Select the usable Wi-Fi, mobile or wired connections. Allow your desktop microphone and notifications; test incoming calls and two-way speech. Secure password saving requires an available, unlocked Secret Service keyring.
7. Keep the computer awake for continuous reception. After waking or reconnecting a cable, check each service’s connection state; reconnect or refresh the USB device if necessary. Sleeping a computer pauses communication.

- The initial native package requires GLIBC 2.38 or newer. Mint 22 / Ubuntu 24.04 are the tested baseline; other desktop environments and distributions still need their own checks.
- Keep the normal application sandbox enabled. If AppImage cannot mount, install your distribution’s compatible FUSE support, or launch with APPIMAGE_EXTRACT_AND_RUN=1. A sandbox error should be diagnosed; --no-sandbox is not the installation procedure.
- Radio GPS position telemetry and the computer’s own GPS are separate. Optional automatic team sharing uses an explicitly configured localhost GPSD receiver with fresh time/accuracy data and your consent. A T1000-E position alone does not verify that GPSD sharing works.

## Update a Linux installation

Linux updates use a separate signed feed from Android. The AppImage and Debian package have different installation steps; a download does not silently install system packages.

1. Open Settings → App features → Updates. Check for an update and download the Linux file offered for your installation. neXt verifies the signed manifest, size and checksum before offering it.
2. For AppImage, use Restart to apply when available. The desktop application replaces its writable AppImage, keeps a rollback copy and restarts with the same data-folder arguments. Keep the AppImage in a folder you own.
3. For .deb, use Show file to locate the verified package, close neXt and open the file in your system package installer to upgrade it. Approve the system confirmation, then reopen neXt. The app does not silently run a privileged package install.
4. Keep your existing data folder and do not delete it to update. Check your identity, interfaces and services after reopening. If an update is cancelled, the existing installed version remains available.
5. If installation fails, retain your data and the verified file. Check disk space, folder permissions and the release instructions; report the version, package type and error without sharing passwords or private keys.

- The first Linux release already contains signed update support. Its linux-stable feed is independent of the Android latest-release feed.
- Back up before upgrades. A rollback application copy is not a backup of your message database.
- Never apply an Android APK on Linux or replace a Linux AppImage with a package intended for another operating system.
