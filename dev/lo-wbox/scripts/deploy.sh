#!/usr/bin/env bash
# deploy.sh — Build and deploy the Nelson extension into the dev profile.
#
# Only does: build .oxt + install via unopkg.
# Does NOT manage soffice/compositor lifecycle — caller handles that
# via kill (before) and launch (after).
#
# Environment (set by wbox-mcp):
#   LO_PROFILE_DIR — LO user profile path
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(cd "$CONFIG_DIR/../.." && pwd)"

PROFILE_DIR="${LO_PROFILE_DIR:-/tmp/lo_dev_profile}"
PROFILE_URI="file://$PROFILE_DIR"
EXTENSION_ID="org.extension.nelson"
OXT_FILE="$PROJECT_ROOT/build/nelson.oxt"

# Find unopkg
UNOPKG=$(command -v unopkg 2>/dev/null || echo "/usr/bin/unopkg")
if [[ ! -x "$UNOPKG" ]]; then
    echo "ERROR: unopkg not found"
    exit 1
fi

echo "=== Deploy ==="
echo "  Project root: $PROJECT_ROOT"
echo "  Profile:      $PROFILE_DIR"

# ── 1. Build .oxt ──────────────────────────────────────────────
echo ""
echo "--- Building .oxt ---"
cd "$PROJECT_ROOT"

python3 scripts/generate_manifest.py
python3 scripts/build_oxt.py --output "$OXT_FILE"
echo "  Built: $OXT_FILE"

# ── 2. Install via unopkg ──────────────────────────────────────
echo ""
echo "--- Installing extension ---"

# A profile that has never had the extension has nothing to remove, and
# unopkg then prints its own "ERROR: ... is not deployed" plus "unopkg
# failed": in deploy.log that reads like a failed deploy. Keep its output
# only when it is about something else.
if ! remove_out=$($UNOPKG remove "$EXTENSION_ID" \
        -env:UserInstallation="$PROFILE_URI" 2>&1); then
    case "$remove_out" in
        *"$EXTENSION_ID"*) echo "  (not installed yet, nothing to remove)" ;;
        *) echo "$remove_out" ;;
    esac
fi
sleep 1

if ! $UNOPKG add "$OXT_FILE" -env:UserInstallation="$PROFILE_URI" 2>&1; then
    echo "ERROR: unopkg add failed"
    exit 1
fi
echo "  Installed OK"

echo ""
echo "=== Deploy complete — use kill+launch to restart soffice ==="
