#!/usr/bin/env bash
# tools/pre_commit_hooks/validate_patch.sh
#
# Pre-commit style patch validation script.
# Runs ``git apply --check`` to verify a patch applies cleanly
# without modifying the working tree.
#
# Usage:
#   ./tools/pre_commit_hooks/validate_patch.sh <patch-file>
#
# Exit codes:
#   0 — patch is valid
#   1 — patch fails validation
#   2 — bad usage (no argument supplied)

set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: validate_patch.sh <patch-file>" >&2
    exit 2
fi

PATCH_FILE="$1"

if [ ! -f "$PATCH_FILE" ]; then
    echo "error: patch file not found: $PATCH_FILE" >&2
    exit 2
fi

echo "Validating patch: $PATCH_FILE"
if git apply --check "$PATCH_FILE"; then
    echo "Patch OK — applies cleanly."
    exit 0
else
    echo "Patch FAILED sanity check." >&2
    exit 1
fi
