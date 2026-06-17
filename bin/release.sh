#!/usr/bin/env bash
# Prepares a release PR for the Cover Time Based integration.
#
# Usage: bin/release.sh <version> [--no-push]
#
# Example: bin/release.sh 4.3.0
#          bin/release.sh 4.3.0-rc.1
#
# This is a pure-Python HA integration: the only version-carrying file is the
# manifest (no frontend build, no npm package). The bundled card ships as static
# ESM, so there is nothing to rebuild here.
#
# What it does:
#   1. Pre-flight: valid semver, on main, clean tree, tag not taken (locally or
#      on origin), local main up to date with origin/main, no leftover
#      chore/release branch.
#   2. Creates the version-less `chore/release` branch, bumps the manifest
#      version (via bin/bump-version.sh), commits a `chore: release` marker,
#      pushes, and opens a PR.
#
# After the PR merges, push the v<version> tag to publish the GitHub Release:
#   git tag v<version> && git push origin v<version>
# The release workflow then publishes the release and, for final releases,
# pushes a follow-up commit bumping main to the next minor (main is unprotected).
#
# The release branch is deliberately version-less: HACS scans every branch and
# complains about version numbers in branch names.

set -euo pipefail

if [ $# -lt 1 ]; then
  echo "usage: $0 <version> [--no-push]" >&2
  exit 2
fi

VERSION="$1"

SEMVER_RE='^[0-9]+\.[0-9]+\.[0-9]+(-(alpha|beta|rc)\.[0-9]+)?$'
if ! [[ "$VERSION" =~ $SEMVER_RE ]]; then
  echo "error: not a valid semver version: $VERSION" >&2
  echo "expected format: MAJOR.MINOR.PATCH or MAJOR.MINOR.PATCH-(alpha|beta|rc).N" >&2
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

# Tag must not exist locally or on origin.
TAG="v$VERSION"
if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
  echo "error: tag $TAG already exists locally" >&2
  exit 1
fi
if git ls-remote --tags origin 2>/dev/null | grep -q "refs/tags/$TAG$"; then
  echo "error: tag $TAG already exists on origin" >&2
  exit 1
fi

# Local main must be up to date with origin/main.
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

BRANCH="chore/release"

# The release branch has a fixed name, so a leftover one from an aborted or
# undeleted prior release would make `git checkout -b` crash mid-run. Catch it
# here, before any work, with a clear message.
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

# Optional --no-push flag for tests.
NO_PUSH=false
if [ "${2:-}" = "--no-push" ]; then
  NO_PUSH=true
fi

git checkout -q -b "$BRANCH"

# Bump the manifest version (shared with the release workflow's next-minor bump
# so they can't drift).
"$(dirname "$0")/bump-version.sh" "$VERSION"

git add -A
# --allow-empty supports the "version already bumped in an earlier feature
# commit" workflow: the release branch still gets a clear `chore: release`
# marker commit for the tag to point at.
git commit --allow-empty -qm "chore: release $TAG"

if [ "$NO_PUSH" = "true" ]; then
  echo "Branch $BRANCH prepared. --no-push given; skipping push and PR creation."
  exit 0
fi

# Push the release branch.
git push -u origin "$BRANCH"

# Open the PR.
gh pr create \
  --title "chore: release $TAG" \
  --body "Release \`$TAG\`: bumps the manifest version to \`$VERSION\`.

After merge, push the tag to publish the GitHub Release:

\`\`\`
git tag $TAG
git push origin $TAG
\`\`\`

The release workflow publishes the GitHub Release and, for final releases,
rolls \`main\` forward to the next minor.
"

echo "Release $TAG branch pushed and PR opened."
