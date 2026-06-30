"""Tests for bin/bump-dev.sh.

Post-release helper that opens a PR rolling main forward to the next minor
(the dev-cycle bump — main is protected, so the release workflow can't push it).

Invokes the real bash script inside a throwaway git repo in tmp_path. All GIT_*
env vars are scrubbed so the subprocess git calls operate on the fixture repo
and never on the parent repo running the test (e.g. under a pre-push hook).
"""

import json
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "bin" / "bump-dev.sh"
MANIFEST_REL = "custom_components/cover_time_based/manifest.json"
BRANCH = "chore/bump-dev"


def _clean_env(extra: dict | None = None) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    if extra:
        env.update(extra)
    return env


def _git(
    *args: str, cwd: Path, check: bool = True, **kwargs
) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=check, env=_clean_env(), **kwargs
    )


def _run(cwd: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env or _clean_env(),
    )


def _init_repo(
    tmp_path: Path, *, branch: str = "main", dirty: bool = False, version: str = "4.3.0"
) -> Path:
    """Create a tiny git repo with a manifest.json at the just-released version."""
    _git("init", "-q", "-b", branch, cwd=tmp_path)
    _git("config", "user.email", "t@test", cwd=tmp_path)
    _git("config", "user.name", "t", cwd=tmp_path)

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
    _git("add", ".", cwd=tmp_path)
    _git("commit", "-qm", "init", cwd=tmp_path)

    if dirty:
        (tmp_path / "dirt").write_text("x")

    return tmp_path


def _manifest_version(repo: Path) -> str:
    return json.loads((repo / MANIFEST_REL).read_text())["version"]


def test_rejects_non_main_branch(tmp_path: Path):
    _init_repo(tmp_path, branch="feature")
    result = _run(tmp_path)
    assert result.returncode != 0
    assert "main" in (result.stdout + result.stderr).lower()


def test_rejects_dirty_tree(tmp_path: Path):
    _init_repo(tmp_path, dirty=True)
    result = _run(tmp_path)
    assert result.returncode != 0
    combined = (result.stdout + result.stderr).lower()
    assert "clean" in combined or "dirty" in combined or "uncommitted" in combined


def test_rejects_existing_bump_branch(tmp_path: Path):
    """A leftover version-less chore/bump-dev branch must be detected up front."""
    _init_repo(tmp_path)
    _git("branch", BRANCH, cwd=tmp_path)
    result = _run(tmp_path, "--no-push")
    assert result.returncode != 0
    assert BRANCH in (result.stdout + result.stderr)


def test_computes_next_minor_and_bumps_manifest(tmp_path: Path):
    _init_repo(tmp_path, version="4.3.0")
    result = _run(tmp_path, "--no-push")
    assert result.returncode == 0, result.stdout + result.stderr

    branches = _git(
        "branch", "--list", BRANCH, cwd=tmp_path, capture_output=True, text=True
    ).stdout
    assert BRANCH in branches

    _git("checkout", "-q", BRANCH, cwd=tmp_path)
    assert _manifest_version(tmp_path) == "4.4.0"

    last_msg = _git(
        "log", "-1", "--format=%s", cwd=tmp_path, capture_output=True, text=True
    ).stdout.strip()
    assert "4.4.0" in last_msg and "development" in last_msg, (
        f"unexpected last commit message: {last_msg!r}"
    )


def test_minor_rollover_increments_as_integer(tmp_path: Path):
    """Next minor must increment numerically (4.9 -> 4.10), not lexically."""
    _init_repo(tmp_path, version="4.9.0")
    result = _run(tmp_path, "--no-push")
    assert result.returncode == 0, result.stdout + result.stderr
    _git("checkout", "-q", BRANCH, cwd=tmp_path)
    assert _manifest_version(tmp_path) == "4.10.0"


def test_pushes_and_opens_pr(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    # Shim gh and git push into a fake bin dir that records calls.
    fake_bin = tmp_path / "fake_bin"
    fake_bin.mkdir()
    log = tmp_path / "calls.log"

    (fake_bin / "gh").write_text(
        f'#!/usr/bin/env bash\necho "gh $*" >> "{log}"\necho https://github.com/fake/repo/pull/1\n'
    )
    (fake_bin / "gh").chmod(0o755)

    real_git = subprocess.check_output(["which", "git"], text=True).strip()
    (fake_bin / "git").write_text(
        f'#!/usr/bin/env bash\nif [ "$1" = "push" ]; then echo "git $*" >> "{log}"; exit 0; fi\nexec {real_git} "$@"\n'
    )
    (fake_bin / "git").chmod(0o755)

    env = _clean_env({"PATH": f"{fake_bin}:{os.environ['PATH']}"})
    result = _run(repo, env=env)
    assert result.returncode == 0, result.stdout + result.stderr

    call_log = log.read_text()
    assert "git push" in call_log
    assert "gh pr create" in call_log
    assert BRANCH in call_log
