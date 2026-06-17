#!/usr/bin/env bash
# Opens a PR that rolls main forward to the next minor for development.
#
# Usage: bin/bump-dev.sh [--no-push]
#
# Run this AFTER a release tag is pushed. release.yml normally pushes the
# next-minor bump straight to main, but this repo's main is protected (PR-only
# + required status checks), so that direct push is rejected. This helper does
# the same bump as a PR instead — run it as yourself so CI triggers and the PR
# is mergeable.
#
# It mirrors bin/release.sh's preflight and the next-minor formula in
# .github/workflows/release.yml, so the three can't drift. The branch is
# deliberately version-less: HACS scans every branch and complains about
# version numbers in branch names.

set -euo pipefail

# Optional --no-push flag for tests.
NO_PUSH=false
if [ "${1:-}" = "--no-push" ]; then
  NO_PUSH=true
fi

MANIFEST="custom_components/cover_time_based/manifest.json"
if [ ! -f "$MANIFEST" ]; then
  echo "error: must be run from the repo root ($MANIFEST not found)" >&2
  exit 1
fi

# Must be on main.
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$CURRENT_BRANCH" != "main" ]; then
  echo "error: must be on main (currently on $CURRENT_BRANCH)" >&2
  exit 1
fi

# Working tree must be clean.
if [ -n "$(git status --porcelain)" ]; then
  echo "error: working tree is not clean; commit or stash first" >&2
  exit 1
fi

BRANCH="chore/bump-dev"

# The branch has a fixed name, so a leftover one from an aborted or undeleted
# prior run would make `git checkout -b` crash mid-run. Catch it up front.
if git rev-parse -q --verify "refs/heads/$BRANCH" >/dev/null; then
  echo "error: branch $BRANCH already exists locally; delete it first:" >&2
  echo "  git branch -D $BRANCH" >&2
  exit 1
fi
if git ls-remote --heads origin "$BRANCH" 2>/dev/null | grep -q "refs/heads/$BRANCH$"; then
  echo "error: branch $BRANCH already exists on origin; delete it first:" >&2
  echo "  git push origin --delete $BRANCH" >&2
  exit 1
fi

# Local main must be up to date with origin/main (skipped if there's no origin,
# e.g. in tests).
if git remote get-url origin >/dev/null 2>&1; then
  git fetch -q origin main
  LOCAL=$(git rev-parse main)
  REMOTE=$(git rev-parse origin/main)
  if [ "$LOCAL" != "$REMOTE" ]; then
    echo "error: local main is not up to date with origin/main" >&2
    echo "  local:  $LOCAL" >&2
    echo "  origin: $REMOTE" >&2
    exit 1
  fi
fi

# Just-released version carried by the manifest.
CURRENT=$(python3 -c "import json; print(json.load(open('$MANIFEST'))['version'])")

# Next minor: mj.(mn+1).0 — the same formula release.yml uses. Strip any
# pre-release suffix first so e.g. 4.3.0-rc.1 still rolls to 4.4.0.
NEXT=$(python3 -c "import sys; mj, mn, _ = sys.argv[1].split('-')[0].split('.'); print(f'{mj}.{int(mn) + 1}.0')" "$CURRENT")

git checkout -q -b "$BRANCH"

# Bump the manifest version (shared with release.sh and the release workflow so
# they can't drift).
"$(dirname "$0")/bump-version.sh" "$NEXT"

git add -A
git commit -qm "chore: bump version to $NEXT for development"

if [ "$NO_PUSH" = "true" ]; then
  echo "Branch $BRANCH prepared (manifest $CURRENT -> $NEXT). --no-push given; skipping push and PR creation."
  exit 0
fi

# Push the bump branch.
git push -u origin "$BRANCH"

# Open the PR.
gh pr create \
  --title "chore: bump version to $NEXT for development" \
  --body "Rolls \`main\` forward to the next minor (\`$NEXT\`) for development, so unreleased work no longer carries the just-released \`$CURRENT\`.

This is the post-release dev-cycle bump. \`release.yml\` normally pushes it
straight to \`main\`, but this repo's \`main\` is protected (PR-only + required
status checks), so it lands as a PR instead.
"

echo "Bump branch $BRANCH pushed and PR opened ($CURRENT -> $NEXT)."
