# SPDX-License-Identifier: 0BSD

"""Reference checks for git-log release changelog notes."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_CHANGELOG = _REPO / "scripts" / "ci" / "github-release-changelog.sh"
_DRAFT = _REPO / "scripts" / "ci" / "github-draft-release-upload-assets.sh"

_BULLET_RE = re.compile(r"^\* ([0-9a-f]{40}) (.+)\.$")


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=_REPO,
        text=True,
        capture_output=True,
        check=True,
        **kwargs,
    )


def test_changelog_script_exists_and_is_executable():
    assert _CHANGELOG.is_file()
    assert os.access(_CHANGELOG, os.X_OK)


def test_changelog_script_bash_syntax():
    subprocess.run(["bash", "-n", str(_CHANGELOG)], check=True, cwd=_REPO)  # nosec: BAN-B607


def test_draft_script_invokes_changelog_helper():
    text = _DRAFT.read_text(encoding="utf-8")
    assert "github-release-changelog.sh" in text
    assert "MESHCHATNEXT_DRAFT_NOTES_ONLY" in text


def test_changelog_v4_8_5_uses_prior_stable_and_full_sha_bullets():
    tags = {
        t.strip()
        for t in _run(["git", "tag", "-l", "v4.8.4", "v4.8.5"]).stdout.splitlines()
    }
    if tags != {"v4.8.4", "v4.8.5"}:
        # Shallow clones in some CI shards may lack tags.
        subprocess.run(  # nosec: BAN-B607
            ["git", "fetch", "--tags", "--depth", "50", "origin"],
            cwd=_REPO,
            check=False,
            capture_output=True,
            text=True,
        )
        tags = {
            t.strip()
            for t in _run(["git", "tag", "-l", "v4.8.4", "v4.8.5"]).stdout.splitlines()
        }
    if tags != {"v4.8.4", "v4.8.5"}:
        import pytest

        pytest.skip("v4.8.4/v4.8.5 tags not available in this clone")

    out = _run(["bash", str(_CHANGELOG), "v4.8.5"]).stdout
    # The script emits raw bullets. The draft script adds the heading and
    # wraps the block in a collapsible <details> section.
    assert not out.startswith("##")
    assert out.lstrip().startswith(("* ", "_No previous tag found"))
    bullets = [ln for ln in out.splitlines() if ln.startswith("* ")]
    assert bullets, "expected at least one changelog bullet"
    for ln in bullets:
        m = _BULLET_RE.match(ln)
        assert m, ln
        subject = m.group(2)
        assert not subject.startswith("docs:")
        assert not subject.startswith("test:")
        assert not subject.startswith("ci:")

    # Previous baseline for a stable tag must be the prior vN tag, not a nightly.
    prev = _run(
        [
            "git",
            "describe",
            "--tags",
            "--abbrev=0",
            "--match",
            "v[0-9]*",
            "--exclude",
            "v4.8.5",
            "v4.8.5^",
        ]
    ).stdout.strip()
    assert prev == "v4.8.4"

    # Every listed commit must be in v4.8.4..v4.8.5.
    range_shas = set(
        _run(["git", "rev-list", "--no-merges", "v4.8.4..v4.8.5"]).stdout.split()
    )
    for ln in bullets:
        sha = _BULLET_RE.match(ln).group(1)
        assert sha in range_shas, sha


def test_draft_notes_only_includes_changelog_then_checksums():
    with tempfile.TemporaryDirectory() as tmp:
        asset = Path(tmp) / "dummy-asset.bin"
        asset.write_bytes(b"meshchatnext-release-notes-oracle\n")
        env = os.environ.copy()
        env["MESHCHATNEXT_DRAFT_NOTES_ONLY"] = "1"
        env["TAG"] = "v4.8.5"
        env.pop("GH_TOKEN", None)
        proc = subprocess.run(  # nosec: BAN-B607
            ["bash", str(_DRAFT), tmp],
            cwd=_REPO,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0 and "unknown tag" in (proc.stderr or ""):
            import pytest

            pytest.skip("v4.8.5 tag not available in this clone")
        assert proc.returncode == 0, proc.stderr
        body = proc.stdout
        assert "<summary><strong>Changelog</strong></summary>" in body
        assert "<summary><strong>SHA256 Checksums</strong></summary>" in body
        assert "<summary><strong>Verification</strong></summary>" in body
        assert "dummy-asset.bin" in body
        assert body.index("Changelog</strong>") < body.index(
            "SHA256 Checksums</strong>"
        )
        assert body.index("SHA256 Checksums</strong>") < body.index(
            "Verification</strong>"
        )
        # Bullet shape: full sha, subject, trailing period.
        if "* " in body:
            assert re.search(r"\* [0-9a-f]{40} .+\.", body)


def test_draft_release_notes_support_current_and_historical_headings(tmp_path):
    """Exercise actual notes generation offline, including section boundaries."""
    import shutil

    fixture = tmp_path / "repository"
    scripts = fixture / "scripts" / "ci"
    scripts.mkdir(parents=True)
    for original in (_DRAFT, _CHANGELOG):
        shutil.copy2(original, scripts / original.name)
    subprocess.run(["git", "init", "-q", str(fixture)], check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Release fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "--allow-empty",
            "-qm",
            "fixture",
        ],
        cwd=fixture,
        check=True,
    )
    subprocess.run(["git", "tag", "v0.1.28"], cwd=fixture, check=True)
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "fixture.bin").write_bytes(b"private-release-fixture")
    env = dict(os.environ, MESHCHATNEXT_DRAFT_NOTES_ONLY="1", TAG="v0.1.28")
    env.pop("GH_TOKEN", None)
    for heading in ("## 0.1.28", "## [0.1.28] - 2026-11-23"):
        (fixture / "CHANGELOG.md").write_text(
            "# Changes\n\n## 0.1.280\n\nWrong newer version\n\n"
            + heading
            + "\n\n- Current release detail\n\n### Upgrade\n\nKeep settings.\n\n"
            "## 0.1.27\n\nWrong older version\n"
        )
        body = subprocess.run(
            ["bash", str(scripts / _DRAFT.name), str(assets)],
            cwd=fixture,
            env=env,
            text=True,
            capture_output=True,
            check=True,
        ).stdout
        assert "<summary><strong>Release Notes</strong></summary>" in body
        assert "Current release detail" in body and "### Upgrade" in body
        assert "Keep settings." in body
        assert "Wrong newer version" not in body and "Wrong older version" not in body
        assert body.index("Release Notes</strong>") < body.index("Changelog</strong>")
