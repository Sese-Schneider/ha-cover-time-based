# Claude Code Instructions

## Git Workflow

- **NEVER commit directly to main** — always create a feature branch first.
- Work from a fork: push branches to your fork and open the PR against
    `Sese-Schneider/ha-cover-time-based` `main` (`gh repo set-default` there).
- **Branch naming**: descriptive (e.g. `fix/relay-feedback`). Never include
    version numbers in branch names — HACS scans all branches and complains
    about non-compliant ones, even after deletion.
- Do NOT merge PRs automatically — wait for user approval.
- When merging a PR (after approval), delete the feature branch.

## Changelog

- Record all user-facing changes in `CHANGELOG.md` under the top
    `## <version> (unreleased)` section (`### Features`, `### Fixes`). Link the
    issue or PR. `bin/release.sh` turns that section into the release notes.

## Code Quality

- Run `bash bin/install-hooks.sh` once per clone/worktree. The committed
    `.githooks/pre-push` mirrors CI: ruff format + lint, translation drift
    (`scripts/check_translations.py` — a missing key in any language is an
    error), docs drift (`scripts/check_docs.py` — adding, removing or renaming a
    module or service without touching README/docs blocks the push), then
    `pytest tests/` and, when the card changed, `npm run test:fe:cov`. Bypass in
    an emergency with `git push --no-verify`.
- Before creating a PR run `ruff check .`, `ruff format .`, `npx pyright`, and
    for the card `npm run lint` and `npm run format:check`.
- CI runs the tests against stable, dev and minimum (HA 2025.2.0) channels;
    the hook only runs against the locally installed HA.
- New user-facing strings must be translated into every language: backend in
    `strings.json` + `translations/<lang>.json`, card in
    `frontend/translations.js`. See `TRANSLATING.md`.
- The `manifest.json` keys must be sorted: `domain`, `name` first, then all
    remaining keys in alphabetical order.
- `docs/superpowers/`, `docs/plans/` and `docs/handoffs/` are gitignored —
    specs, plans and handoffs are local working files; never commit them.

## Integration Layout

- Component lives in `custom_components/cover_time_based/`; the configuration
    card is static ESM under `frontend/` (no build step).
- Domain: `cover_time_based`. Alias in `~/workspace/tools/worktree.py`: `cover`.
- Main HA dev container: `ha-cover-main` (start with `ha-wt cover-main`).
- Feature worktrees: `/new-worktree cover <branch>`.
