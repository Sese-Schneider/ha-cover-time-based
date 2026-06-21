"""Tests for bin/changelog-section.sh.

Extracts a single version's section from CHANGELOG.md so the release workflow
can use the hand-written, user-facing changes as the GitHub Release notes
instead of an auto-generated commit list.
"""

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "bin" / "changelog-section.sh"

FIXTURE = """\
## 4.5.0-rc.1 (2026-07-01)

### Features

- Pre-release only feature.

## 4.4.0 (2026-06-18)

### Breaking changes

- Breaking thing happened.

### Features

- Feature one.
- Feature two.

## 4.3.0 (2026-06-17)

### Features

- Older feature.

## 4.2.0 (2026-06-02)

### Fixes

- Oldest fix.
"""


def _clean_env() -> dict:
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def _run(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        env=_clean_env(),
    )


def _make_changelog(tmp_path: Path, content: str = FIXTURE) -> Path:
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text(content)
    return tmp_path


def test_extracts_top_section(tmp_path: Path):
    _make_changelog(tmp_path)
    result = _run(tmp_path, "4.5.0-rc.1")
    assert result.returncode == 0, result.stderr
    assert "Pre-release only feature." in result.stdout
    # Must not bleed into the next section.
    assert "Breaking thing happened." not in result.stdout
    assert "## 4.4.0" not in result.stdout


def test_extracts_middle_section(tmp_path: Path):
    _make_changelog(tmp_path)
    result = _run(tmp_path, "4.4.0")
    assert result.returncode == 0, result.stderr
    assert "Breaking thing happened." in result.stdout
    assert "Feature one." in result.stdout
    assert "Feature two." in result.stdout
    # Neither the previous nor the next section leaks in.
    assert "Pre-release only feature." not in result.stdout
    assert "Older feature." not in result.stdout
    assert "## 4.3.0" not in result.stdout


def test_extracts_last_section(tmp_path: Path):
    _make_changelog(tmp_path)
    result = _run(tmp_path, "4.2.0")
    assert result.returncode == 0, result.stderr
    assert "Oldest fix." in result.stdout
    assert "Older feature." not in result.stdout


def test_version_header_line_is_omitted(tmp_path: Path):
    _make_changelog(tmp_path)
    result = _run(tmp_path, "4.4.0")
    assert result.returncode == 0, result.stderr
    assert "## 4.4.0" not in result.stdout


def test_blank_lines_trimmed_but_interior_preserved(tmp_path: Path):
    _make_changelog(tmp_path)
    result = _run(tmp_path, "4.4.0")
    assert result.returncode == 0, result.stderr
    # No leading/trailing blank lines.
    assert result.stdout.startswith("### Breaking changes")
    assert result.stdout.rstrip("\n").endswith("- Feature two.")
    # Interior blank line between the two subsections survives.
    assert "\n\n### Features\n" in result.stdout


def test_missing_version_exits_nonzero_with_no_output(tmp_path: Path):
    _make_changelog(tmp_path)
    result = _run(tmp_path, "9.9.9")
    assert result.returncode == 1
    assert result.stdout == ""


def test_substring_version_not_mismatched(tmp_path: Path):
    """`4.2.0` must not match a header for `14.2.0` or `4.2.00`."""
    content = "## 14.2.0 (2026-01-01)\n\n### Fixes\n\n- Wrong section.\n"
    _make_changelog(tmp_path, content)
    result = _run(tmp_path, "4.2.0")
    assert result.returncode == 1
    assert result.stdout == ""


def test_handles_crlf_line_endings(tmp_path: Path):
    """The real CHANGELOG.md is CRLF; blank lines must still trim and the
    output must be normalized to LF (no stray carriage returns)."""
    cl = tmp_path / "CHANGELOG.md"
    cl.write_bytes(FIXTURE.replace("\n", "\r\n").encode())
    result = _run(tmp_path, "4.4.0")
    assert result.returncode == 0, result.stderr
    # Blank (CRLF) lines around the section must still be trimmed.
    assert result.stdout.startswith("### Breaking changes")
    assert result.stdout.rstrip("\n").endswith("- Feature two.")
    assert "\n\n### Features\n" in result.stdout
    assert "## 4.3.0" not in result.stdout


def test_section_not_truncated_by_non_version_hash_heading(tmp_path: Path):
    """A `## ` line that isn't a version header (a prose subheading, or a
    comment inside a fenced code block) is release-note content, not the next
    section — the section ends only at the next *version* heading."""
    content = (
        "## 4.4.0 (2026-06-18)\n\n"
        "### Features\n\n- A feature.\n\n"
        "## Upgrade notes\n\nDo the thing.\n\n"
        "## 4.3.0 (2026-06-17)\n\n### Features\n\n- Old feature.\n"
    )
    _make_changelog(tmp_path, content)
    result = _run(tmp_path, "4.4.0")
    assert result.returncode == 0, result.stderr
    assert "A feature." in result.stdout
    assert "## Upgrade notes" in result.stdout
    assert "Do the thing." in result.stdout
    # The real next version still bounds the section.
    assert "Old feature." not in result.stdout
    assert "## 4.3.0" not in result.stdout


def test_missing_changelog_file_errors(tmp_path: Path):
    result = _run(tmp_path, "4.4.0")
    assert result.returncode == 2
    assert "not found" in (result.stdout + result.stderr).lower()


def test_missing_version_arg_exits_2(tmp_path: Path):
    """No version argument is a usage error (exit 2), distinct from exit 1."""
    _make_changelog(tmp_path)
    result = _run(tmp_path)
    assert result.returncode == 2
    assert "usage" in (result.stdout + result.stderr).lower()


def test_empty_body_section_exits_1(tmp_path: Path):
    """A header with no body (an unfilled stub) is treated as no section."""
    content = "## 4.4.0 (2026-06-18)\n\n## 4.3.0 (2026-06-17)\n\n- Old.\n"
    _make_changelog(tmp_path, content)
    result = _run(tmp_path, "4.4.0")
    assert result.returncode == 1
    assert result.stdout == ""


def test_real_changelog_known_version():
    """Against the repo's real CHANGELOG.md, 4.4.0 yields its own section only."""
    result = _run(REPO_ROOT, "4.4.0")
    assert result.returncode == 0, result.stderr
    assert "Breaking changes" in result.stdout
    # Does not leak the previous released section's header.
    assert "## 4.3.0" not in result.stdout
