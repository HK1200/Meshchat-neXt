# SPDX-License-Identifier: 0BSD
# Runtime checks remain enforced under python -O.
"""Check the actual frozen interpreter through a disposable, isolated API."""

import argparse
import http.client
import json
import os
import signal
import socket
import ssl
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--arch", choices=["x64", "arm64"], required=True)
    parser.add_argument(
        "--expected-python", default=os.getenv("PYTHON_VERSION", "3.14.10")
    )
    parser.add_argument("--inside", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--ci-privileged-setup", action="store_true", help=argparse.SUPPRESS
    )
    parser.add_argument("--fixture", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not sys.platform.startswith("linux"):
        raise RuntimeError("Build invariant failed: sys.platform.startswith('linux')")
    hosted_ci = (
        os.environ.get("GITHUB_ACTIONS") == "true"
        and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted"
    )
    if args.ci_privileged_setup and (not hosted_ci or os.geteuid() != 0 or args.inside):
        raise RuntimeError("Privileged namespace setup is restricted to hosted CI")
    if hosted_ci and os.geteuid() != 0 and not args.inside:
        # Ubuntu restricts unprivileged namespace capabilities. Only the
        # disposable hosted fixture uses privileged setup; no host policy changes.
        clean_env = [
            "PATH=/usr/sbin:/usr/bin:/sbin:/bin",
            "LANG=C.UTF-8",
            "GITHUB_ACTIONS=true",
            "RUNNER_ENVIRONMENT=github-hosted",
        ]
        if os.environ.get("LD_LIBRARY_PATH"):
            clean_env.append("LD_LIBRARY_PATH=" + os.environ["LD_LIBRARY_PATH"])
        subprocess.run(
            [
                "/usr/bin/sudo",
                "-n",
                "/usr/bin/env",
                "-i",
                *clean_env,
                sys.executable,
                str(Path(__file__).resolve()),
                "--ci-privileged-setup",
                "--arch",
                args.arch,
                "--expected-python",
                args.expected_python,
            ],
            check=True,
            timeout=120,
        )
        return
    root = Path(__file__).resolve().parents[2]
    build = root / f"build/exe/linux-{args.arch}"
    candidates = [
        build / n
        for n in ("MeshchatNext", "ReticulumMeshChatX")
        if (build / n).is_file()
    ]
    if not len(candidates) == 1:
        raise RuntimeError(candidates)
    binary = candidates[0].resolve()
    temp = root / "temp-tests"
    temp.mkdir(exist_ok=True)
    if not args.inside:
        with tempfile.TemporaryDirectory(
            prefix="frozen-python-", dir=temp
        ) as directory:
            fixture = Path(directory).resolve()
            (fixture / "home").mkdir()
            (fixture / "tmp").mkdir(mode=448)
            (fixture / "reticulum").mkdir()
            (fixture / "reticulum/config").write_text(
                "[reticulum]\nshare_instance=No\nenable_transport=No\n\n[interfaces]\n"
            )
            env = {
                **os.environ,
                "FROZEN_PROBE_PARENT_NETNS": os.readlink("/proc/self/ns/net"),
                "FROZEN_PROBE_PARENT_USERNS": os.readlink("/proc/self/ns/user"),
                "MESHCHAT_FORCE_WEB_AUDIO": "1",
            }
            for key in (
                "DBUS_SESSION_BUS_ADDRESS",
                "DISPLAY",
                "WAYLAND_DISPLAY",
                "PULSE_SERVER",
            ):
                env.pop(key, None)
            command = [
                "bwrap",
                "--ro-bind",
                "/",
                "/",
                "--bind",
                str(fixture),
                str(fixture),
                "--proc",
                "/proc",
                "--dev",
                "/dev",
                "--tmpfs",
                "/run",
                "--unshare-user",
                "--unshare-pid",
                "--unshare-net",
                "--cap-drop",
                "ALL",
                "--die-with-parent",
                "--setenv",
                "TMPDIR",
                str(fixture / "tmp"),
                "--setenv",
                "TMP",
                str(fixture / "tmp"),
                "--setenv",
                "TEMP",
                str(fixture / "tmp"),
                "--setenv",
                "HOME",
                str(fixture / "home"),
                sys.executable,
                str(Path(__file__).resolve()),
                "--inside",
                "--fixture",
                str(fixture),
                "--arch",
                args.arch,
                "--expected-python",
                args.expected_python,
            ]
            try:
                subprocess.run(command, env=env, cwd=root, check=True, timeout=120)
            except subprocess.CalledProcessError:
                log = fixture / "backend.log"
                if log.exists():
                    print(log.read_text(errors="replace")[-10000:], file=sys.stderr)
                raise
            report = json.loads((fixture / "result.json").read_text())
            output = root / f"reports/frozen-python-{args.arch}.json"
            output.parent.mkdir(exist_ok=True)
            output.write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps(report))
        return
    fixture = args.fixture.resolve()
    if not (
        fixture.is_relative_to(temp.resolve())
        and fixture.name.startswith("frozen-python-")
    ):
        raise RuntimeError(
            "Build invariant failed: fixture.is_relative_to(temp.resolve()) and fixture.name.startswith('frozen-python-')"
        )
    parent_net = os.environ.get("FROZEN_PROBE_PARENT_NETNS")
    if not (parent_net and parent_net != os.readlink("/proc/self/ns/net")):
        raise RuntimeError(
            "Build invariant failed: parent_net and parent_net != os.readlink('/proc/self/ns/net')"
        )
    parent_user = os.environ.get("FROZEN_PROBE_PARENT_USERNS")
    if not (parent_user and parent_user != os.readlink("/proc/self/ns/user")):
        raise RuntimeError("Frozen runtime probe requires a separate user namespace")
    status = dict(
        line.split(":", 1)
        for line in Path("/proc/self/status").read_text().splitlines()
        if ":" in line
    )
    if any(int(status[key].strip(), 16) != 0 for key in ("CapEff", "CapBnd")):
        raise RuntimeError(
            "Frozen runtime payload must have no effective or bounding capabilities"
        )
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    command = [
        str(binary),
        "--headless",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--storage-dir",
        str(fixture / "storage"),
        "--reticulum-config-dir",
        str(fixture / "reticulum"),
    ]
    with (fixture / "backend.log").open("w") as log:
        process = subprocess.Popen(
            command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True
        )
        try:
            deadline = time.monotonic() + 90
            last = "backend not ready"
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError("Frozen backend exited before metadata")
                try:
                    certificate = fixture / "storage/ssl/cert.pem"
                    context = ssl.create_default_context(cafile=str(certificate))
                    connection = http.client.HTTPSConnection(
                        "localhost", port, context=context, timeout=3
                    )
                    try:
                        connection.request(
                            "GET",
                            "/api/v1/app/info",
                            headers={"Origin": f"https://localhost:{port}"},
                        )
                        response = connection.getresponse()
                        if response.status != 200:
                            raise ConnectionError(
                                f"Metadata returned HTTP {response.status}"
                            )
                        info = json.loads(response.read())["app_info"]
                    finally:
                        connection.close()
                    break
                except (OSError, http.client.HTTPException) as error:
                    last = str(error)
                    time.sleep(0.25)
            else:
                raise AssertionError(last)
            actual = info["python_version"]
            if not actual == args.expected_python:
                raise RuntimeError(
                    {"expected": args.expected_python, "actual_frozen_python": actual}
                )
            report = {
                "passed": True,
                "expected_python": args.expected_python,
                "actual_frozen_python": actual,
                "source": info.get("git_commit"),
                "private_network_and_devices": True,
                "private_user_namespace": True,
                "payload_capabilities_dropped": True,
                "payload_uid": os.geteuid(),
                "namespace_setup": "privileged-hosted-ci"
                if hosted_ci
                else "unprivileged-local",
                "fixture_certificate_verified": True,
            }
            (fixture / "result.json").write_text(json.dumps(report))
        finally:
            try:
                process.send_signal(signal.SIGINT)
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=5)


if __name__ == "__main__":
    main()
