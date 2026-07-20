"""Tests for scripts/check_translations.py.

Guards the translation drift gate the pre-push hook and CI run. Two kinds of
drift matter, and both must fail the build:

- a *stale* key, left in a translations/<lang>.json after being renamed or
  removed in strings.json — dead weight that can mask a typo;
- a *missing* key, present in strings.json but never translated — which ships
  an untranslated string to that language with nothing to notice it.
"""

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check_translations.py"

STRINGS = {
    "config": {"step": {"user": {"title": "Add a cover", "data": {"name": "Name"}}}},
    "services": {"set_known_position": {"name": "Set position"}},
}


def build_component(tmp_path: Path, translations: dict[str, dict]) -> Path:
    """A minimal component dir: strings.json plus the given catalogues."""
    component = tmp_path / "my_component"
    (component / "translations").mkdir(parents=True)
    (component / "strings.json").write_text(json.dumps(STRINGS), encoding="utf-8")
    for lang, payload in translations.items():
        (component / "translations" / f"{lang}.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )
    return component


def run(component: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(component)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_complete_translation_passes(tmp_path):
    result = run(build_component(tmp_path, {"pt": STRINGS}))
    assert result.returncode == 0, result.stdout


def test_missing_key_is_an_error(tmp_path):
    """A key in strings.json that a catalogue never translated must fail.

    Otherwise a new English string merges, nobody translates it, and every
    non-English user silently reads English with a green build.
    """
    partial = {
        "config": {"step": {"user": {"title": "Adicionar", "data": {"name": "Nome"}}}},
        # services.set_known_position.name never translated
    }
    result = run(build_component(tmp_path, {"pt": partial}))
    assert result.returncode == 1, result.stdout


def test_missing_key_output_names_the_key(tmp_path):
    """Naming the key is what makes the failure actionable."""
    partial = {
        "config": {"step": {"user": {"title": "Adicionar", "data": {"name": "Nome"}}}},
    }
    result = run(build_component(tmp_path, {"pt": partial}))
    assert "services.set_known_position.name" in result.stdout
    assert "pt.json" in result.stdout


def test_stale_key_is_still_an_error(tmp_path):
    """The pre-existing guard must survive the missing-key change."""
    with_extra = json.loads(json.dumps(STRINGS))
    with_extra["config"]["step"]["user"]["removed_long_ago"] = "Sobra"
    result = run(build_component(tmp_path, {"pt": with_extra}))
    assert result.returncode == 1, result.stdout
    assert "removed_long_ago" in result.stdout


def test_reports_every_offending_language_not_just_the_first(tmp_path):
    """A contributor should see the whole job, not fix-and-rerun once per file."""
    partial = {
        "config": {"step": {"user": {"title": "T", "data": {"name": "N"}}}},
    }
    result = run(build_component(tmp_path, {"pl": partial, "pt": partial}))
    assert result.returncode == 1, result.stdout
    assert "pl.json" in result.stdout
    assert "pt.json" in result.stdout


def test_no_translations_dir_passes(tmp_path):
    component = tmp_path / "bare"
    component.mkdir()
    (component / "strings.json").write_text(json.dumps(STRINGS), encoding="utf-8")
    result = run(component)
    assert result.returncode == 0, result.stdout


def test_real_repo_translations_are_complete():
    """The shipped catalogues must satisfy the gate this script enforces."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout
