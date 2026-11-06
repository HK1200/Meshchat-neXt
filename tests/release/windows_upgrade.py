# SPDX-License-Identifier: 0BSD
import hashlib
import json
import os
import subprocess
import time
import uuid
import zipfile
from pathlib import Path

import requests

ROOT = Path(os.environ["MESHCHAT_RELEASE_REVIEW_ROOT"]).resolve()
assert ROOT.parent.name == "temp-tests" and (ROOT / "source/.git").exists()
TEST = ROOT / "upgrade-validation" / ("test-" + uuid.uuid4().hex[:8])
APP = TEST / "app"
PROFILE = TEST / "profile"
PORT = 19445
TEST.mkdir(parents=True)
env = os.environ.copy()
for key, sub in [
    ("APPDATA", "appdata"),
    ("LOCALAPPDATA", "localappdata"),
    ("TEMP", "tmp"),
    ("TMP", "tmp"),
]:
    env[key] = str(TEST / sub)
    (TEST / sub).mkdir(exist_ok=True)
env["MESHCHAT_DATA_DIR"] = str(PROFILE)
env["MESHCHATNEXT_UPDATE_DISABLED"] = "1"
env["MESHCHAT_APPCONTAINER"] = "0"
env.pop("AIOHTTP_NOSENDFILE", None)
config = PROFILE / ".reticulum/config"
config.parent.mkdir(parents=True)
config.write_text(
    "[reticulum]\n  enable_transport = No\n  share_instance = No\n  discover_interfaces = No\n  autoconnect_discovered_interfaces = 0\n[logging]\n  loglevel = 4\n[interfaces]\n"
)
URL = f"https://127.0.0.1:{PORT}"
process = None
session = None
report = {"test_root": str(TEST), "production_profiles_modified": False}


def run(args, log, timeout=180):
    with (TEST / log).open("w") as f:
        result = subprocess.run(
            [str(a) for a in args],
            env=env,
            stdout=f,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=timeout,
        )
    assert result.returncode == 0, (log, result.returncode)


def start(label):
    global process, session
    exe = APP / "resources/backend/MeshchatNext.exe"
    with (TEST / (label + ".log")).open("w") as f:
        process = subprocess.Popen(
            [
                str(exe),
                "--headless",
                "--host",
                "127.0.0.1",
                "--port",
                str(PORT),
                "--data-dir",
                str(PROFILE),
            ],
            env=env,
            stdout=f,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    session = requests.Session()
    session.trust_env = False
    session.verify = str(PROFILE / "storage/ssl/cert.pem")
    for _ in range(90):
        assert process.poll() is None, "Backend exited during " + label
        try:
            response = session.get(URL + "/api/v1/auth/csrf", timeout=2)
            response.raise_for_status()
            session.headers["X-CSRF-Token"] = response.json()["csrf_token"]
            ready = session.get(URL + "/api/v1/telephone/contacts", timeout=2)
            ready.raise_for_status()
            return
        except (requests.RequestException, OSError):
            time.sleep(1)
    raise RuntimeError("Startup timeout " + label)


def api(method, path, **kwargs):
    response = session.request(method, URL + "/api/v1/" + path, timeout=60, **kwargs)
    response.raise_for_status()
    return response


def stop():
    global process
    if process and process.poll() is None:
        try:
            api("POST", "app/shutdown")
        except requests.RequestException:
            pass
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=10)
    process = None


def snapshot():
    return {
        str(p.relative_to(PROFILE)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in PROFILE.rglob("*")
        if p.is_file()
    }


try:
    old = ROOT / "old/MeshchatNext-v0.1.6-win-x64-installer.exe"
    new = ROOT / "source/dist/MeshchatNext-v0.1.7-win-x64-installer.exe"
    assert old.is_file() and new.is_file()
    run([old, "/S", "/D=" + str(APP)], "install-baseline.log")
    start("baseline-backend")
    marker = "Synthetic Windows upgrade contact " + uuid.uuid4().hex[:8]
    api(
        "POST",
        "telephone/contacts",
        json={"name": marker, "remote_identity_hash": "11" * 16},
    )
    import sqlite3

    message_marker = "Synthetic offline upgrade message " + uuid.uuid4().hex[:8]
    inserted = False
    for db in PROFILE.rglob("*.db"):
        with sqlite3.connect(db) as connection:
            if connection.execute(
                "SELECT 1 FROM sqlite_master WHERE name='lxmf_messages'"
            ).fetchone():
                connection.execute(
                    "INSERT INTO lxmf_messages (hash,source_hash,destination_hash,peer_hash,state,is_incoming,content,fields,timestamp) VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        uuid.uuid4().hex * 2,
                        "22" * 16,
                        "11" * 16,
                        "22" * 16,
                        "delivered",
                        1,
                        message_marker,
                        "{}",
                        time.time(),
                    ),
                )
                inserted = True
    assert inserted, "Synthetic message database not found"
    report["synthetic_incoming_message_inserted_without_network_send"] = True
    backup = TEST / "baseline-backup.zip"
    backup.write_bytes(api("POST", "database/backup/download").content)
    with zipfile.ZipFile(backup) as z:
        assert z.testzip() is None
    report["baseline_backup_zip"] = "passed"
    stop()
    before = snapshot()
    assert before
    report["profile_file_count_before"] = len(before)
    run([new, "/S", "/D=" + str(APP)], "install-corrected-in-place.log")
    assert snapshot() == before, "Installer changed profile bytes"
    report["in_place_upgrade_preserves_all_profile_bytes"] = True
    # Independently verify the Publisher users see in Windows installed apps.
    import winreg

    publishers = []
    for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Uninstall",
            0,
            winreg.KEY_READ | view,
        ) as registry:
            index = 0
            while True:
                try:
                    name = winreg.EnumKey(registry, index)
                except OSError:
                    break
                index += 1
                try:
                    with winreg.OpenKey(registry, name) as entry:
                        location = (
                            winreg.QueryValueEx(entry, "DisplayIcon")[0]
                            .rsplit(",", 1)[0]
                            .strip('"')
                        )
                        if (
                            Path(location).resolve()
                            == (APP / "Meshchat neXt.exe").resolve()
                        ):
                            publishers.append(
                                winreg.QueryValueEx(entry, "Publisher")[0]
                            )
                except OSError:
                    continue
    assert publishers and set(publishers) == {"HK1200"}, publishers
    report["installed_windows_publisher"] = "HK1200"
    expected = hashlib.sha256(
        (ROOT / "source/dist/win-unpacked/Meshchat neXt.exe").read_bytes()
    ).hexdigest()
    assert (
        hashlib.sha256((APP / "Meshchat neXt.exe").read_bytes()).hexdigest() == expected
    )
    report["corrected_executable_installed"] = True
    report["baseline_version"] = "0.1.6"
    report["upgraded_version"] = "0.1.7"
    start("corrected-backend")
    assert api("GET", "app/info").json()["app_info"]["version"] == "0.1.7"
    assert api("GET", "app/info").json()["app_info"]["python_version"] == "3.14.10"
    assert (
        api("GET", "app/info").json()["app_info"]["git_commit"]
        == "c73b4e0b5f5376f9e4e6a0e9b752bf00a76f67f1"
    )
    assert api("GET", "app/info").json()["app_info"]["build_channel"] == "stable"
    assert api("GET", "app/info").json()["app_info"]["is_dev_build"] is False
    report["installed_stable_channel"] = True
    report["installed_is_dev_build"] = False
    report["installed_patched_python_version"] = "3.14.10"
    worker_env = {
        k: v for k, v in os.environ.items() if k not in {"PYTHONHOME", "PYTHONPATH"}
    }
    worker = subprocess.run(
        [
            str(APP / "resources/backend/MeshchatNext.exe"),
            "--meshchatnext-run-module",
            "meshchatnext.src.backend.frozen_freeze_probe",
        ],
        cwd=TEST,
        env=worker_env,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert worker.returncode == 0, (worker.stdout, worker.stderr)
    assert "frozen-freeze-probe ok" in worker.stdout
    assert not worker.stderr.strip(), worker.stderr
    report["installed_frozen_worker_probe"] = {"passed": True, "stderr_empty": True}
    assert marker in api("GET", "telephone/contacts").text
    report["contact_persisted_after_upgrade"] = True
    newbackup = TEST / "corrected-backup.zip"
    newbackup.write_bytes(api("POST", "database/backup/download").content)
    with zipfile.ZipFile(newbackup) as z:
        assert z.testzip() is None
    stop()
    restore = TEST / "restored-profile"
    run(
        [
            APP / "resources/backend/MeshchatNext.exe",
            "--headless",
            "--data-dir",
            restore,
            "--restore-db",
            newbackup,
        ],
        "restore-backup.log",
    )
    report["backup_restore_command"] = "passed"
    restored_dbs = list(restore.rglob("*.db"))
    import sqlite3

    found = False
    message_found = False
    for db in restored_dbs:
        with sqlite3.connect(db) as conn:
            tables = [
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            ]
            if "contacts" in tables:
                found = (
                    any(
                        marker in str(row)
                        for row in conn.execute("SELECT * FROM contacts")
                    )
                    or found
                )
            if "lxmf_messages" in tables:
                message_found = (
                    conn.execute(
                        "SELECT 1 FROM lxmf_messages WHERE content=?", (message_marker,)
                    ).fetchone()
                    is not None
                    or message_found
                )
    assert found, "Restored contact missing"
    assert message_found, "Restored synthetic message missing"
    report["synthetic_message_restored_from_backup"] = True
    report["contact_restored_from_backup"] = True
    before_uninstall = snapshot()
    uninstallers = list(APP.glob("*Uninstall*.exe"))
    assert len(uninstallers) == 1
    assert uninstallers[0].resolve().is_relative_to(TEST.resolve())
    run([uninstallers[0], "/S"], "uninstall.log")
    for _ in range(30):
        if not (APP / "Meshchat neXt.exe").exists():
            break
        time.sleep(0.5)
    assert not (APP / "Meshchat neXt.exe").exists()
    assert snapshot() == before_uninstall, "Uninstaller changed profile"
    report["uninstall_preserves_profile_bytes"] = True
    report["status"] = "passed"
except Exception as exc:
    report.update(status="failed", error=str(exc))
    raise
finally:
    stop()
    (ROOT / "upgrade-validation.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
