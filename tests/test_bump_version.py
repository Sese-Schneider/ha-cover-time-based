"""Tests for bin/bump-version.sh."""

import json
import os
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "bin" / "bump-version.sh"
MANIFEST_REL = "custom_components/cover_time_based/manifest.json"


def _clean_env(extra: dict | None = None) -> dict:
    """Return os.environ with all GIT_* vars stripped, plus any extras."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    if extra:
        env.update(extra)
    return env


def _run(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        env=_clean_env(),
    )


def _make_tmp_repo(tmp_path: Path, version: str = "4.2.0") -> Path:
    """Create a minimal tree with a manifest.json carrying the given version."""
    manifest = tmp_path / MANIFEST_REL
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(
            {
                "domain": "cover_time_based",
                "name": "Cover Time Based",
                "version": version,
            },
            indent=2,
        )
        + "\n"
    )
    return tmp_path


def test_validate_rejects_bad_semver(tmp_path: Path):
    _make_tmp_repo(tmp_path)
    before = (tmp_path / MANIFEST_REL).read_text()
    result = _run(tmp_path, "--validate", "not-a-version")
    assert result.returncode != 0
    assert "semver" in (result.stdout + result.stderr).lower()
    # --validate must not write anything.
    assert (tmp_path / MANIFEST_REL).read_text() == before


def test_validate_accepts_good_semver(tmp_path: Path):
    _make_tmp_repo(tmp_path)
    before = (tmp_path / MANIFEST_REL).read_text()
    for v in ("4.3.0", "5.0.0", "4.3.0-alpha.1", "4.3.0-beta.2", "4.3.0-rc.1"):
        result = _run(tmp_path, "--validate", v)
        assert result.returncode == 0, f"{v}: {result.stdout + result.stderr}"
    # --validate must not write anything.
    assert (tmp_path / MANIFEST_REL).read_text() == before


def test_bump_rewrites_manifest(tmp_path: Path):
    _make_tmp_repo(tmp_path, version="4.2.0")
    result = _run(tmp_path, "4.3.0")
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads((tmp_path / MANIFEST_REL).read_text())
    assert data["version"] == "4.3.0"
    # Other keys preserved.
    assert data["domain"] == "cover_time_based"


def test_bump_rejects_bad_semver(tmp_path: Path):
    _make_tmp_repo(tmp_path)
    before = (tmp_path / MANIFEST_REL).read_text()
    result = _run(tmp_path, "not-a-version")
    assert result.returncode != 0
    assert "semver" in (result.stdout + result.stderr).lower()
    assert (tmp_path / MANIFEST_REL).read_text() == before


def test_bump_fails_when_manifest_missing(tmp_path: Path):
    result = _run(tmp_path, "4.3.0")
    assert result.returncode != 0
    assert "not found" in (result.stdout + result.stderr).lower()


def test_bump_on_copy_of_real_manifest(tmp_path: Path):
    """Bumping a copy of the real repo manifest works and preserves key order."""
    src = REPO_ROOT / MANIFEST_REL
    dst = tmp_path / MANIFEST_REL
    dst.parent.mkdir(parents=True)
    shutil.copy(src, dst)
    keys_before = list(json.loads(dst.read_text()).keys())

    result = _run(tmp_path, "9.9.9")
    assert result.returncode == 0, result.stdout + result.stderr

    data = json.loads(dst.read_text())
    assert data["version"] == "9.9.9"
    assert list(data.keys()) == keys_before, "manifest key order must be preserved"
