#!/usr/bin/env bash
# Prints the CHANGELOG.md section for a single version, for use as the GitHub
# Release notes — so a release shows the hand-written, user-facing changes
# instead of an auto-generated commit/PR list.
#
# Usage: bin/changelog-section.sh <version> [changelog-path]
#   bin/changelog-section.sh 4.4.0
#
# Prints everything under the `## <version> (date)` header up to the next `## `
# header, with the version header itself omitted (the release already shows the
# version) and surrounding blank lines trimmed (interior blanks preserved).
#
# Exits 1 (printing nothing) when the version has no section — the caller can
# then fall back to auto-generated notes, e.g. for a pre-release tag that has no
# changelog entry yet. Exits 2 on usage error or a missing changelog file.

set -euo pipefail

VERSION="${1:-}"
CHANGELOG="${2:-CHANGELOG.md}"

if [ -z "$VERSION" ]; then
  echo "usage: $0 <version> [changelog-path]" >&2
  exit 2
fi

if [ ! -f "$CHANGELOG" ]; then
  echo "error: changelog not found: $CHANGELOG" >&2
  exit 2
fi

# Match the target header by exact version field ($2), so `4.2.0` never matches
# a `## 14.2.0` or `## 4.2.00` header. The section ends only at the next *version*
# `## ` header — a non-version `## ` line (a prose subheading, or a comment in a
# fenced code block) is body content, not a boundary, so it is kept. Drop only
# leading blank lines (the `seen` guard); trailing blanks are stripped by the
# `$(...)` capture below, which re-adds one newline.
section="$(
  awk -v ver="$VERSION" '
    { sub(/\r$/, "") }  # normalize CRLF; a lone \r else reads as a field (NF>0)
    /^## / && insec && $2 ~ /^[0-9]+\.[0-9]+\.[0-9]+/ { exit }   # next version
    /^## / && !insec && $2 == ver { insec = 1; next }            # target header
    insec { if (NF) seen = 1; if (seen) print }
  ' "$CHANGELOG"
)"

if [ -z "$section" ]; then
  exit 1
fi

printf '%s\n' "$section"
