"""Tests for bin/release.sh.

Invokes the real bash script inside a throwaway git repo in tmp_path. All GIT_*
env vars are scrubbed so the subprocess git calls operate on the fixture repo
and never on the parent repo running the test (e.g. under a pre-push hook).
"""

import json
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "bin" / "release.sh"
MANIFEST_REL = "custom_components/cover_time_based/manifest.json"


def _clean_env(extra: dict | None = None) -> dict:
    """Return os.environ with all GIT_* vars stripped, plus any extras.

    Without this, subprocess git calls in tests inherit GIT_DIR / GIT_WORK_TREE /
    GIT_INDEX_FILE from a parent context (e.g. a pre-push hook) and operate on
    the wrong repo.
    """
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    if extra:
        env.update(extra)
    return env


def _git(
    *args: str, cwd: Path, check: bool = True, **kwargs
) -> subprocess.CompletedProcess:
    """Run a git command with GIT_* env scrubbed."""
    return subprocess.run(
        ["git", *args], cwd=cwd, check=check, env=_clean_env(), **kwargs
    )


def _run(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        env=_clean_env(),
    )


def test_rejects_invalid_semver(tmp_path: Path):
    result = _run(tmp_path, "not-a-version")
    assert result.returncode != 0
    assert "semver" in (result.stdout + result.stderr).lower()


def test_accepts_alpha_suffix(tmp_path: Path):
    """Pre-flight should accept alpha pre-release suffix at the semver check.
    Other pre-flights (clean tree, on main, etc.) will still fail in tmp_path,
    so we only check that the error is NOT a semver error."""
    result = _run(tmp_path, "4.3.0-alpha.1")
    combined = (result.stdout + result.stderr).lower()
    assert "semver" not in combined


def test_accepts_beta_suffix(tmp_path: Path):
    result = _run(tmp_path, "4.3.0-beta.2")
    combined = (result.stdout + result.stderr).lower()
    assert "semver" not in combined


def test_accepts_rc_suffix(tmp_path: Path):
    result = _run(tmp_path, "4.3.0-rc.1")
    combined = (result.stdout + result.stderr).lower()
    assert "semver" not in combined


def _init_repo(
    tmp_path: Path, *, branch: str = "main", dirty: bool = False, version: str = "4.2.0"
) -> Path:
    """Create a tiny git repo with a manifest.json on the named branch."""
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
    _git("tag", f"v{version}", cwd=tmp_path)

    if dirty:
        (tmp_path / "dirt").write_text("x")

    return tmp_path


def test_rejects_non_main_branch(tmp_path: Path):
    _init_repo(tmp_path, branch="feature")
    result = _run(tmp_path, "4.3.0")
    assert result.returncode != 0
    assert "main" in (result.stdout + result.stderr).lower()


def test_rejects_dirty_tree(tmp_path: Path):
    _init_repo(tmp_path, dirty=True)
    result = _run(tmp_path, "4.3.0")
    assert result.returncode != 0
    combined = (result.stdout + result.stderr).lower()
    assert "clean" in combined or "dirty" in combined or "uncommitted" in combined


def test_rejects_existing_tag(tmp_path: Path):
    _init_repo(tmp_path)
    result = _run(tmp_path, "4.2.0")  # tag v4.2.0 already exists
    assert result.returncode != 0
    assert "tag" in (result.stdout + result.stderr).lower()


def test_rejects_main_behind_origin(tmp_path: Path):
    """If local main has fewer commits than origin/main, fail."""
    origin = tmp_path / "origin.git"
    _git("init", "-q", "--bare", "-b", "main", str(origin), cwd=tmp_path)

    local = tmp_path / "local"
    local.mkdir()
    _init_repo(local)
    _git("remote", "add", "origin", str(origin), cwd=local)
    _git("push", "-q", "origin", "main", "--tags", cwd=local)

    # Add a commit on origin that local doesn't have.
    other = tmp_path / "other"
    _git("clone", "-q", str(origin), str(other), cwd=tmp_path)
    _git("config", "user.email", "t@test", cwd=other)
    _git("config", "user.name", "t", cwd=other)
    (other / "new.txt").write_text("x")
    _git("add", ".", cwd=other)
    _git("commit", "-qm", "new", cwd=other)
    _git("push", "-q", "origin", "main", cwd=other)

    result = _run(local, "4.3.0")
    assert result.returncode != 0
    combined = (result.stdout + result.stderr).lower()
    assert "up to date" in combined or "behind" in combined


def test_rejects_existing_release_branch(tmp_path: Path):
    """A leftover version-less chore/release branch must be detected up front."""
    _init_repo(tmp_path)
    _git("branch", "chore/release", cwd=tmp_path)
    result = _run(tmp_path, "4.3.0")
    assert result.returncode != 0
    assert "chore/release" in (result.stdout + result.stderr)


def test_integration_release_bumps_manifest(tmp_path: Path):
    _init_repo(tmp_path)
    result = _run(tmp_path, "4.3.0", "--no-push")
    assert result.returncode == 0, result.stdout + result.stderr

    # Version-less release branch exists.
    branches = _git(
        "branch",
        "--list",
        "chore/release",
        cwd=tmp_path,
        capture_output=True,
        text=True,
    ).stdout
    assert "chore/release" in branches

    # Switch to it and inspect the manifest.
    _git("checkout", "-q", "chore/release", cwd=tmp_path)
    data = json.loads((tmp_path / MANIFEST_REL).read_text())
    assert data["version"] == "4.3.0"

    # A chore: release marker commit sits on top.
    last_msg = _git(
        "log", "-1", "--format=%s", cwd=tmp_path, capture_output=True, text=True
    ).stdout.strip()
    assert "release v4.3.0" in last_msg, f"unexpected last commit message: {last_msg!r}"


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
    result = subprocess.run(
        ["bash", str(SCRIPT), "4.3.0"],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    call_log = log.read_text()
    assert "git push" in call_log
    assert "gh pr create" in call_log
    assert "chore/release" in call_log


def test_does_not_leak_to_parent_git_dir_via_env(tmp_path: Path, monkeypatch):
    """If GIT_DIR is set in the env (e.g. by a hook), tests must not write to
    that repo. Regression for the bug where fixture git config leaked into the
    main repo's config during a pre-push hook run."""
    parent = tmp_path / "parent_repo"
    parent.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(parent)], check=True)
    parent_git = parent / ".git"
    config_before = (parent_git / "config").read_text()

    monkeypatch.setenv("GIT_DIR", str(parent_git))

    fixture = tmp_path / "fixture"
    fixture.mkdir()
    _init_repo(fixture)

    config_after = (parent_git / "config").read_text()
    assert config_before == config_after, (
        f"_init_repo leaked into GIT_DIR config:\n--- before ---\n{config_before}\n--- after ---\n{config_after}"
    )
