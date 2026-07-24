#!/usr/bin/env bash
#
# release.sh — disciplined, one-command release for the Nelson MCP extension.
#
# There is intentionally no CI auto-release: the build is not hermetic (needs a
# LibreOffice SDK, wrapped in Docker) and the .oxt bundles a Windows-specific
# pysqlite3 payload whose ABI must match LibreOffice's Python. So releases are
# cut by a human — this script just makes that safe and repeatable.
#
# What it does, in order:
#   1. Pre-flight discipline gates (branch, clean tree, pushed, changelog, tag).
#   2. Fetch the Windows pysqlite3 payload (platform-independent download) so the
#      asset is Windows-complete even when built on Linux.
#   3. Build the .oxt via `make build`.
#   4. HARD GATE: verify the built .oxt actually contains the pysqlite3 payload.
#   5. Tag vX.Y.Z, push the tag, create the GitHub release with the .oxt asset
#      and release notes extracted from CHANGELOG.md.
#
# Usage:
#   scripts/release.sh              # interactive: builds, verifies, asks before publishing
#   scripts/release.sh --dry-run    # everything except tag/push/publish
#   scripts/release.sh --yes        # skip the final confirmation prompt
#
# The version is read from plugin/version.py — bump it and update CHANGELOG.md
# BEFORE running this.

set -euo pipefail

# ── Locate repo root ─────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

DRY_RUN=0
ASSUME_YES=0
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        --yes|-y)  ASSUME_YES=1 ;;
        *) echo "Unknown argument: $arg" >&2; exit 2 ;;
    esac
done

# ── Tiny output helpers ──────────────────────────────────────────────────────
step() { printf '\n\033[1;34m▶ %s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
die()  { printf '\n\033[1;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }

PYTHON="${PYTHON:-python3}"
LO_PYTHON_VERSION="${LO_PYTHON_VERSION:-3.12}"

# ── Read version ─────────────────────────────────────────────────────────────
VERSION="$("$PYTHON" -c 'from plugin.version import EXTENSION_VERSION; print(EXTENSION_VERSION)')"
BUILD_TAG="$("$PYTHON" -c 'from plugin.version import BUILD_TAG; print(BUILD_TAG)')"
TAG="v${VERSION}"
ASSET="build/nelson-${VERSION}.oxt"

step "Releasing Nelson MCP ${TAG}"
[ "$DRY_RUN" = 1 ] && warn "DRY RUN — nothing will be tagged, pushed, or published"

# ── Gate 1: clean semver (no BUILD_TAG) ──────────────────────────────────────
step "Pre-flight discipline gates"
[ -z "$BUILD_TAG" ] || die "BUILD_TAG is '$BUILD_TAG' — reset it to '' in plugin/version.py for a clean release."
ok "BUILD_TAG empty (clean semver ${VERSION})"

# ── Gate 2: tooling ──────────────────────────────────────────────────────────
command -v gh   >/dev/null || die "'gh' (GitHub CLI) not found."
command -v git  >/dev/null || die "'git' not found."
gh auth status >/dev/null 2>&1 || die "'gh' is not authenticated — run 'gh auth login'."
ok "gh authenticated"

# ── Gate 3: on main ──────────────────────────────────────────────────────────
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
[ "$BRANCH" = "main" ] || die "Not on 'main' (on '$BRANCH'). Releases are cut from main."
ok "on branch main"

# ── Gate 4: no uncommitted *tracked* changes ─────────────────────────────────
# Untracked files can't affect the build or the tag, so they only warn.
[ -z "$(git status --porcelain --untracked-files=no)" ] \
    || die "Uncommitted changes to tracked files. Commit or stash first."
UNTRACKED="$(git ls-files --others --exclude-standard)"
if [ -n "$UNTRACKED" ]; then
    warn "untracked files present (not part of this release):"
    echo "$UNTRACKED" | sed 's/^/      /'
else
    ok "working tree clean"
fi

# ── Gate 5: local == origin/main (everything pushed) ─────────────────────────
git fetch --quiet origin main
LOCAL="$(git rev-parse @)"
REMOTE="$(git rev-parse origin/main)"
[ "$LOCAL" = "$REMOTE" ] || die "Local main differs from origin/main — push (or pull) first."
ok "main is in sync with origin"

# ── Gate 6: tag does not already exist ───────────────────────────────────────
if git rev-parse -q --verify "refs/tags/${TAG}" >/dev/null; then
    die "Tag ${TAG} already exists locally."
fi
if git ls-remote --exit-code --tags origin "refs/tags/${TAG}" >/dev/null 2>&1; then
    die "Tag ${TAG} already exists on origin."
fi
if gh release view "${TAG}" >/dev/null 2>&1; then
    die "A GitHub release ${TAG} already exists."
fi
ok "tag ${TAG} is free"

# ── Gate 7: CHANGELOG has a section for this version ──────────────────────────
NOTES_FILE="$(mktemp)"
trap 'rm -f "$NOTES_FILE"' EXIT
# Extract the block between "## [VERSION]" and the next "## [".
awk -v ver="$VERSION" '
    $0 ~ "^## \\[" ver "\\]" { grab=1; next }
    grab && /^## \[/ { exit }
    grab { print }
' CHANGELOG.md > "$NOTES_FILE"
if ! grep -q '[^[:space:]]' "$NOTES_FILE"; then
    die "CHANGELOG.md has no '## [${VERSION}]' section (or it is empty). Add release notes first."
fi
ok "CHANGELOG section for ${VERSION} found"

# ── Build: fetch Windows sqlite payload, then build the .oxt ──────────────────
step "Fetching Windows pysqlite3 payload (host-independent)"
"$PYTHON" scripts/fetch_sqlite3.py --python-version "$LO_PYTHON_VERSION"
ok "pysqlite3 payload staged in build/sqlite3_win/"

step "Building the .oxt (make build)"
make build
[ -f build/nelson.oxt ] || die "make build did not produce build/nelson.oxt"
cp build/nelson.oxt "$ASSET"
ok "built ${ASSET}"

# ── HARD GATE: the asset must contain the Windows pysqlite3 payload ───────────
step "Verifying the asset is Windows-complete"
if command -v unzip >/dev/null; then
    LISTING="$(unzip -Z1 "$ASSET")"
else
    LISTING="$("$PYTHON" -c 'import sys,zipfile; print("\n".join(zipfile.ZipFile(sys.argv[1]).namelist()))' "$ASSET")"
fi
echo "$LISTING" | grep -q 'plugin/lib/pysqlite3/' \
    || die "Asset is missing plugin/lib/pysqlite3/ — a Linux build without the sqlite payload would break on Windows. Aborting."
ok "pysqlite3 payload present in the .oxt"

# ── Summary before the point of no return ────────────────────────────────────
step "Ready to publish"
echo "  Version : ${VERSION}"
echo "  Tag     : ${TAG}"
echo "  Asset   : ${ASSET}"
echo "  Notes   : (from CHANGELOG.md)"
sed 's/^/    /' "$NOTES_FILE"

if [ "$DRY_RUN" = 1 ]; then
    step "Dry run complete — not tagging or publishing."
    echo "  Re-run without --dry-run to publish."
    exit 0
fi

if [ "$ASSUME_YES" != 1 ]; then
    printf '\nProceed to tag %s, push it, and create the GitHub release? [y/N] ' "$TAG"
    read -r reply
    case "$reply" in
        y|Y|yes|YES) ;;
        *) die "Aborted by user. Nothing was tagged or published." ;;
    esac
fi

# ── Publish ──────────────────────────────────────────────────────────────────
step "Tagging and pushing ${TAG}"
FIRST_LINE="$(head -n1 "$NOTES_FILE")"
git tag -a "$TAG" -m "Release ${TAG}"
git push origin "$TAG"
ok "pushed ${TAG}"

step "Creating GitHub release"
gh release create "$TAG" "$ASSET" \
    --title "$TAG" \
    --notes-file "$NOTES_FILE"
ok "release ${TAG} published"

step "Done — ${TAG} is live"
echo "  Verify: gh release view ${TAG}"
echo
warn "Windows check: this asset was not registration-tested on a non-UTF-8 / CJK Windows box."
warn "If you can, smoke-test 'unopkg add' on Windows before announcing it as latest."
